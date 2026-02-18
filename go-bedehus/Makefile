APP_NAME := bedehus
ON_NAME := bedehus-on
OFF_NAME := bedehus-off
CONFIG_PATH := ../config/config.json
OUT_DIR := dist

.PHONY: tidy build build-on build-off run run-on run-off clean build-linux-amd64 build-pi1 build-pi2-3 build-pi4-arm64 build-all

tidy:
	go mod tidy

build:
	go build -o $(APP_NAME) .

build-on:
	go build -o $(ON_NAME) ./cmd/on

build-off:
	go build -o $(OFF_NAME) ./cmd/off

run:
	BEDEHUS_BASE_DIR=$(abspath ..) go run . -config $(CONFIG_PATH)

run-on:
	BEDEHUS_BASE_DIR=$(abspath ..) go run ./cmd/on -config $(CONFIG_PATH)

run-off:
	BEDEHUS_BASE_DIR=$(abspath ..) go run ./cmd/off -config $(CONFIG_PATH)

clean:
	rm -rf $(OUT_DIR)

build-linux-amd64:
	mkdir -p $(OUT_DIR)
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o $(OUT_DIR)/$(APP_NAME)-linux-amd64 .
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o $(OUT_DIR)/$(ON_NAME)-linux-amd64 ./cmd/on
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o $(OUT_DIR)/$(OFF_NAME)-linux-amd64 ./cmd/off

build-pi1:
	mkdir -p $(OUT_DIR)
	CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=6 go build -o $(OUT_DIR)/$(APP_NAME)-linux-armv6 .
	CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=6 go build -o $(OUT_DIR)/$(ON_NAME)-linux-armv6 ./cmd/on
	CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=6 go build -o $(OUT_DIR)/$(OFF_NAME)-linux-armv6 ./cmd/off

build-pi2-3:
	mkdir -p $(OUT_DIR)
	CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -o $(OUT_DIR)/$(APP_NAME)-linux-armv7 .
	CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -o $(OUT_DIR)/$(ON_NAME)-linux-armv7 ./cmd/on
	CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=7 go build -o $(OUT_DIR)/$(OFF_NAME)-linux-armv7 ./cmd/off

build-pi4-arm64:
	mkdir -p $(OUT_DIR)
	# Pi 3 og Pi 4 med 64-bit OS bruker arm64
	CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o $(OUT_DIR)/$(APP_NAME)-linux-arm64 .
	CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o $(OUT_DIR)/$(ON_NAME)-linux-arm64 ./cmd/on
	CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o $(OUT_DIR)/$(OFF_NAME)-linux-arm64 ./cmd/off

build-all: build-linux-amd64 build-pi1 build-pi2-3 build-pi4-arm64
