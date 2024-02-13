package main

import (
	"log"
	"os"
)

func main() {
	// Create a log file
	logFile, err := os.OpenFile("basiclogging.log", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0666)
	if err != nil {
		log.Fatal(err)
	}
	defer logFile.Close()

	// Set the output of the standard logger to the log file
	log.SetOutput(logFile)

	// Example of logging
	log.Println("This is a test log entry")
}

