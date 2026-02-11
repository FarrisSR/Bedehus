APP_NAME := bedehus
CONFIG_PATH := ../config/config.json
OUT_DIR := dist

.PHONY: tidy build run clean build-linux-amd64 build-pi1 build-pi2-3 build-pi4-arm64 build-all

tidy:
	go mod tidy

build:
	go build -o $(APP_NAME) .

run:
	BEDEHUS_BASE_DIR=$(abspath ..) go run . -config $(CONFIG_PATH)

clean:
	rm -rf $(OUT_DIR)

build-linux-amd64:
	mkdir -p $(OUT_DIR)
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o $(OUT_DIR)/$(APP_NAME)-linux-amd64 .

build-pi1:
	mkdir -p $(OUT_DIR)
	CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=6 go build -o $(OUT_DIR)/$(APP_NAME)-linux-armv6 .

build-pi2-3:
	mkdir -p $(OUT_DIR)
	CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -o $(OUT_DIR)/$(APP_NAME)-linux-armv7 .

build-pi4-arm64:
	mkdir -p $(OUT_DIR)
	# Pi 3 og Pi 4 med 64-bit OS bruker arm64
	CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o $(OUT_DIR)/$(APP_NAME)-linux-arm64 .

build-all: build-linux-amd64 build-pi1 build-pi2-3 build-pi4-arm64
