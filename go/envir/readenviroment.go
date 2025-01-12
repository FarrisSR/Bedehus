package main

import (
	"log"
	"os"
	"strings"
)

func main() {
	// Example of reading an environment variable
	//useMock := os.Getenv("USE_MOCK_SR201")
	// Read the environment variable and convert to lowercase
	useMock := strings.ToLower(os.Getenv("USE_MOCK_SR201"))

	if useMock == "true" {
		log.Println("Using mock SR201")
	} else {
		log.Println("Using real SR201")
	}
}

