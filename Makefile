.PHONY: deploy

deploy:
	docker-compose down
	docker-compose build api webapp
	docker-compose up -d
