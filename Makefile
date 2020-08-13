.PHONY: help pull build clean
.DEFAULT_GOAL: build

help:
	@echo "make pull"
	@echo "       Start docker container with pull"
	@echo "make build"
	@echo "       Start docker container rebuilding container"

pull:
	docker-compose up

build:
	docker-compose -f docker-compose_dev.yml up --build

clean:
	docker system prune -a
