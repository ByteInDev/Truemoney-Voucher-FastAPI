.PHONY: run install quality test docker-build deploy deploy-local

run:
	python -m app.main

install:
	python -m pip install -r requirements.txt

quality:
	python -m compileall -q app

test:
	python -m pytest -q

docker-build:
	docker build -t truemoney-voucher -f deployments/Dockerfile .

deploy:
	@echo "Deploying to remote server..."
	ssh zelthr@192.168.1.111 "mkdir -p /home/zelthr/truemoney-voucher"
	scp -r app requirements.txt .env.example zelthr@192.168.1.111:/home/zelthr/truemoney-voucher/
	ssh zelthr@192.168.1.111 "cd /home/zelthr/truemoney-voucher && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && (pkill -f 'uvicorn app.main' || true) && nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 3000 > api.log 2>&1 &"
	@echo "Deployment complete! Service running on http://192.168.1.111:3000"

deploy-local:
	@echo "Deploying locally with Docker..."
	docker build -t truemoney-voucher -f deployments/Dockerfile .
	docker run -d -p 3000:3000 --name truemoney-voucher truemoney-voucher
	@echo "Local deployment complete! Service running on http://localhost:3000"