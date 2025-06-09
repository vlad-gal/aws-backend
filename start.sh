#!/bin/bash

cd "$(dirname "$0")"

python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt

uvicorn app:app --host 0.0.0.0 --port 80