package main

import (
    "fmt"
    "net"
    "time"
)

const (
    HOST = "127.0.0.1"
    PORT = "6722"
    currentstatus = "000000"
)

func main() {
    listener, err := net.Listen("tcp", HOST+":"+PORT)
    if err != nil {
        fmt.Println("Unable to bind to socket:", err)
        return
    }
    defer listener.Close()

    fmt.Println("Listening on", HOST+":"+PORT)

    for {
        conn, err := listener.Accept()
        if err != nil {
            fmt.Println("Error accepting connection:", err)
            return
        }
        fmt.Println("Connected by", conn.RemoteAddr())

        go handleRequest(conn)
    }
}

func handleRequest(conn net.Conn) {
    defer conn.Close()

    data := make([]byte, 8)
    _, err := conn.Read(data)
    if err != nil {
        fmt.Println("Error reading data:", err)
        return
    }

    if string(data) == "00" {
        fmt.Println("Asking for Current status")
        conn.SetWriteDeadline(time.Now().Add(5 * time.Second))
        _, err = conn.Write([]byte(currentstatus))
        if err != nil {
            fmt.Println("Error occured while sending data:", err)
        } else {
            fmt.Println("Data sent successfully")
        }
    }
}
