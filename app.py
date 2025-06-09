from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import boto3
import os
import requests
import random

# DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://user:password@localhost:3306/image_metadata")

# engine = create_engine(DATABASE_URL)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base = declarative_base()

app = FastAPI()
s3 = boto3.client("s3")
S3_BUCKET = os.getenv("S3_BUCKET_NAME", "default-bucket")


# class ImageMetadata(Base):
#     __tablename__ = "images"
#
#     id = Column(Integer, primary_key=True, index=True)
#     name = Column(String, unique=True, nullable=False)
#     size = Column(Integer)
#     extension = Column(String)
#     last_modified = Column(DateTime, default=datetime.utcnow)
#
#
# Base.metadata.create_all(bind=engine)


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
    content = await file.read()
    filename = file.filename
    size = len(content)
    extension = filename.split(".")[-1]

    s3.upload_fileobj(File(...), S3_BUCKET, filename)

    # db = SessionLocal()
    # db_image = ImageMetadata(
    #     name=filename,
    #     size=size,
    #     extension=extension,
    #     last_modified=datetime.now()
    # )
    # db.add(db_image)
    # db.commit()
    # db.close()
    return {"message": "Image uploaded successfully."}


@app.get("/download/{name}")
def download_image(name: str):
    try:
        file_path = f"/tmp/{name}"
        s3.download_file(S3_BUCKET, name, file_path)
        return FileResponse(file_path, media_type="application/octet-stream", filename=name)
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")


@app.get("/metadata/{name}")
def get_metadata(name: str):
    # db = SessionLocal()
    # image = db.query(ImageMetadata).filter(ImageMetadata.name == name).first()
    # db.close()
    # if image:
    #     return {
    #         "name": image.name,
    #         "size": image.size,
    #         "extension": image.extension,
    #         "last_modified": image.last_modified
    #     }
    raise HTTPException(status_code=404, detail="Metadata not found")


@app.get("/metadata/random")
def get_random_metadata():
    # db = SessionLocal()
    # images = db.query(ImageMetadata).all()
    # db.close()
    # if images:
    #     image = random.choice(images)
    #     return {
    #         "name": image.name,
    #         "size": image.size,
    #         "extension": image.extension,
    #         "last_modified": image.last_modified
    #     }
    raise HTTPException(status_code=404, detail="No images found")


@app.delete("/delete/{name}")
def delete_image(name: str):
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=name)
        # db = SessionLocal()
        # image = db.query(ImageMetadata).filter(ImageMetadata.name == name).first()
        # if image:
        #     db.delete(image)
        #     db.commit()
        # db.close()
        return {"message": "Image deleted successfully."}
    except Exception:
        raise HTTPException(status_code=500, detail="Error deleting image")
