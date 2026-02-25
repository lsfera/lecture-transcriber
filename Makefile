IMAGE ?= lecture-transcriber:latest
DOCKERFILE ?= Dockerfile
CONTAINER_NAME ?= lecture-transcriber
DISPLAY ?= $(IP):0
RUN_ARGS ?=

.PHONY: docker-build docker-run

docker-build:
	docker build --progress=plain -f $(DOCKERFILE) -t $(IMAGE) .

docker-run:
	docker run --rm \
		--name $(CONTAINER_NAME) \
		--volumes-from $$(hostname) \
		-e DISPLAY=$(DISPLAY) \
		$(if $(GROQ_API_KEY),-e GROQ_API_KEY=$(GROQ_API_KEY),) \
		$(RUN_ARGS) \
		$(IMAGE)
