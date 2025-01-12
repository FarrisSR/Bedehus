package main

import (
	"Bedehus/sr201" // Import the sr201 package
	//"github.com/FarrisSR/gosr201" // Import the sr201 package
	"log"
	//"/home/runo/code/Bedehus/go/sr201/" // Import the sr201 package
)

func main() {
	// Create a configuration for the SR201 device
	config := sr201.Config{
		IP:       "192.168.100.100", // Replace with your device's IP
		Port:     "6722",            // Replace with your device's port
		Protocol: "tcp",             // Use "tcp" or "udp"
		Relay:    1,                 // Relay number to operate on
	}

	// Create a new SR201 instance
	device, err := sr201.NewSR201(config)
	if err != nil {
		log.Fatalf("Failed to connect to SR201: %v", err)
	}
	defer device.Close() // Ensure the connection is closed when done

	// Perform actions
	// 1. Check the status of the relay
	err = device.ExecuteAction("status")
	if err != nil {
		log.Fatalf("Error checking status: %v", err)
	}

	// 2. Close the relay
	err = device.ExecuteAction("close")
	if err != nil {
		log.Fatalf("Error closing relay: %v", err)
	}

	// 3. Check the status of the relay
	err = device.ExecuteAction("status")
	if err != nil {
		log.Fatalf("Error checking status: %v", err)
	}

	// 4. Open the relay
	err = device.ExecuteAction("open")
	if err != nil {
		log.Fatalf("Error opening relay: %v", err)
	}

	// 5. Check the status of the relay
	err = device.ExecuteAction("status")
	if err != nil {
		log.Fatalf("Error checking status: %v", err)
	}

}
