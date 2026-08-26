ifeq (,$(wildcard .env))
$(error .env file is missing at . Please create one based on .env.example)
endif

include .env	
	
build-clipagent:
	docker compose build

start-clipagent:
	docker compose up --build -d

stop-clipagent:
	docker compose stop
