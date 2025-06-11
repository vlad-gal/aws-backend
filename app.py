import io
import json
import random
from datetime import datetime, time

import boto3
import requests
from fastapi import FastAPI, UploadFile, File, HTTPException
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from starlette.responses import StreamingResponse

app = FastAPI()
boto3.setup_default_session(region_name='us-east-1')
s3 = boto3.client("s3")
ssm = boto3.client("ssm")
sqs = boto3.client("sqs")
sns = boto3.client("sns")

S3_BUCKET = ssm.get_parameter(Name="bucket")["Parameter"]["Value"]
DB_URL = ssm.get_parameter(Name="/db/url")["Parameter"]["Value"]
DB_PASSWORD = ssm.get_parameter(Name="/db/password", WithDecryption=True)["Parameter"]["Value"]
DB_USERNAME = ssm.get_parameter(Name="/db/username")["Parameter"]["Value"]
SNS_TOPIC_ARN = ssm.get_parameter(Name="sns_topic")["Parameter"]["Value"]
SQS_URL = ssm.get_parameter(Name="sqs_queue")["Parameter"]["Value"]
DNS_NAME = ssm.get_parameter(Name="dns_name")["Parameter"]["Value"]

engine = create_engine(f"mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}@{DB_URL}:3306/image_metadata")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ImageMetadata(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    size = Column(Integer)
    extension = Column(String(10))
    last_modified = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


@app.get("/")
def get_az_and_region():
    try:
        token_response = requests.put(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            timeout=2
        )
        token = token_response.text

        az_response = requests.get(
            "http://169.254.169.254/latest/meta-data/placement/availability-zone",
            headers={"X-aws-ec2-metadata-token": token},
            timeout=2
        )
        az = az_response.text
        region = az[:-1]
        return {"availability_zone": az, "region": region}
    except Exception as e:
        return {"error": str(e)}


@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    try:
        filename = file.filename
        extension = filename.split(".")[-1]

        content = await file.read()
        size = len(content)

        buffer = io.BytesIO(content)

        s3.upload_fileobj(buffer, S3_BUCKET, filename)

        db = SessionLocal()

        db_image = ImageMetadata(
            name=filename,
            size=size,
            extension=extension,
            last_modified=datetime.utcnow()
        )
        db.add(db_image)
        db.commit()

        message = {
            "event": "ImageUploaded",
            "name": filename,
            "size": size,
            "extension": extension
        }
        sqs.send_message(
            QueueUrl=SQS_URL,
            MessageBody=json.dumps(message)
        )

        return {"message": "Image uploaded", "name": filename, "size": size}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/download/{name}")
def download_image(name: str):
    try:
        file_stream = io.BytesIO()
        s3.download_fileobj(S3_BUCKET, name, file_stream)
        file_stream.seek(0)
        media_type = "application/octet-stream"
        if name.lower().endswith((".jpg", ".jpeg")):
            media_type = "image/jpeg"
        elif name.lower().endswith(".png"):
            media_type = "image/png"

        return StreamingResponse(
            file_stream,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={name}"}
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail="Image not found")


@app.get("/metadata/{name}")
def get_metadata(name: str):
    db = SessionLocal()
    image = db.query(ImageMetadata).filter(ImageMetadata.name == name).first()
    db.close()
    if image:
        return {
            "name": image.name,
            "size": image.size,
            "extension": image.extension,
            "last_modified": image.last_modified
        }
    raise HTTPException(status_code=404, detail="Metadata not found")


@app.get("/random")
def get_random_metadata():
    db = SessionLocal()
    images = db.query(ImageMetadata).all()
    db.close()
    if images:
        image = random.choice(images)
        return {
            "name": image.name,
            "size": image.size,
            "extension": image.extension,
            "last_modified": image.last_modified
        }
    raise HTTPException(status_code=404, detail="No images found")


@app.delete("/delete/{name}")
def delete_image(name: str):
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=name)
        db = SessionLocal()
        image = db.query(ImageMetadata).filter(ImageMetadata.name == name).first()
        if image:
            db.delete(image)
            db.commit()
        db.close()
        return {"message": "Image deleted successfully."}
    except Exception:
        raise HTTPException(status_code=500, detail="Error deleting image")


@app.post("/subscribe")
def subscribe(email: str):
    sns.subscribe(
        TopicArn=SNS_TOPIC_ARN,
        Protocol="email",
        Endpoint=email
    )
    return {"message": f"Confirmation email sent to {email}"}


@app.post("/unsubscribe")
def unsubscribe(email: str):
    subscriptions = sns.list_subscriptions_by_topic(TopicArn=SNS_TOPIC_ARN)["Subscriptions"]
    for sub in subscriptions:
        if sub["Endpoint"] == email:
            sns.unsubscribe(SubscriptionArn=sub["SubscriptionArn"])
            return {"message": f"Unsubscribed {email}"}
    return {"error": "Subscription not found"}, 404


@app.on_event("startup")
def start_sqs_to_sns_worker():
    import threading
    threading.Thread(target=process_queue, daemon=True).start()


def process_queue():
    while True:
        response = sqs.receive_message(
            QueueUrl=SQS_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=10
        )
        for msg in response.get("Messages", []):
            body = json.loads(msg["Body"])
            message_text = (
                f"New image uploaded!\n"
                f"Name: {body['name']}\n"
                f"Size: {body['size']} bytes\n"
                f"Extension: {body['extension']}\n"
                f"Download: {DNS_NAME}/download/{body['name']}"
            )
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=message_text,
                MessageAttributes={
                    "extension": {
                        "DataType": "String",
                        "StringValue": body.get("extension", "unknown")
                    }
                }
            )
            sqs.delete_message(
                QueueUrl=SQS_URL,
                ReceiptHandle=msg["ReceiptHandle"]
            )
        time.sleep(5)
