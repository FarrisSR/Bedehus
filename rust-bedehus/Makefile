APP_NAME := bedehus-rs
BIN_DIR := bin

.PHONY: build install clean test

build:
	cargo build --release

install: build
	mkdir -p $(BIN_DIR)
	install -m 755 target/release/$(APP_NAME) $(BIN_DIR)/$(APP_NAME)

test:
	cargo test

clean:
	cargo clean
	rm -rf $(BIN_DIR)
