from fastapi import FastAPI
import requests

app = FastAPI()

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
