#include <iostream>
#include <string>
#include <boost/asio.hpp>

using boost::asio::ip::tcp;

const std::string currentstatus = "000000";

int main()
{
    boost::asio::io_context io_context;

    tcp::acceptor acceptor(io_context, tcp::endpoint(tcp::v4(), 6722));

    while (true)
    {
        tcp::socket socket(io_context);
        acceptor.accept(socket);

        std::cout << "Connected by " << socket.remote_endpoint() << std::endl;

        std::string data;
        boost::asio::streambuf buf;
        boost::asio::read_until(socket, buf, '\n');
        std::istream input(&buf);
        input >> data;

        if (data == "00")
        {
            std::cout << "Asking for Current status" << std::endl;
            boost::asio::write(socket, boost::asio::buffer(currentstatus));
            std::cout << "Data sent successfully" << std::endl;
        }
    }

    return 0;
}
