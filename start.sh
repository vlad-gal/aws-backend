#!/bin/bash

cd "$(dirname "$0")"

python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt


APP_DIR="/opt/myapp/aws-backend"
VENV_DIR="$APP_DIR/venv"
USER="root"

cat <<EOF > /etc/systemd/system/backend.service
[Unit]
Description=backend
After=network.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/uvicorn app:app --host 0.0.0.0 --port 80
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable backend
systemctl restart backend
systemctl status backend
