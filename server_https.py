#!/usr/bin/env python3
"""HTTPS launcher for the Tashiro Ironworks Receipt OCR system."""

from __future__ import annotations

import ssl
from pathlib import Path

import uvicorn

from app.main import create_app


def main() -> None:
	project_root = Path(__file__).parent
	cert_dir = project_root / "certs"
	key_path = cert_dir / "dev-key.pem"
	cert_path = cert_dir / "dev-cert.pem"

	if not key_path.exists() or not cert_path.exists():
		raise FileNotFoundError(
			"Missing TLS certificate or key. Generate them with:\n"
			"  mkdir certs\n"
			"  openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/dev-key.pem "
			"-out certs/dev-cert.pem -days 365 -subj \"/CN=TashiroOCR\""
		)

	app = create_app()

	ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
	ssl_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

	print("🏭 Tashiro Ironworks Receipt OCR System (HTTPS mode)")
	print("=" * 60)
	print("🔐 Serving securely over HTTPS")
	print("📱 Mobile interface: https://<your-ip>:8443/mobile")
	print("🖥️  Desktop interface: https://localhost:8443/")
	print("📚 API Documentation: https://<your-ip>:8443/docs")
	print("=" * 60)

	uvicorn.run(
		app,
		host="0.0.0.0",
		port=8443,
		ssl=ssl_context,
		reload=False,
		access_log=True,
	)


if __name__ == "__main__":
	main()
