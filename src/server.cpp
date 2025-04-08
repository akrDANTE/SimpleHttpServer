#include <iostream>
#include <cstdlib>
#include <string>
#include <cstring>
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <sstream>
#include <vector>
#include <utility>
#include <unordered_map>
#include <thread>
#include <fstream>

constexpr int MAX_REQUEST_LEN = 2048;

struct Client{
  int fd;
  struct sockaddr_in addr;
  
  void disconnect()
  {
    close(fd);
  }
};

class HttpListener{
public:
  HttpListener(int port): port(port), server_running(false), connection_backlog(5)
  {
    server_running = init();
  }

  bool init()
  {
    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if(server_fd < 0)
    {
      std::cout << "Error in initializing server!!\n";
      perror("socket");
      return false;
    }

    int reuse = 1;
    if(setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse)) < 0)
    {
      std::cout << "setsockopt failed\n";
      perror("setsockopt");
      return false;
    }

    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(port);
    memset(server_addr.sin_zero, '\0', sizeof(server_addr.sin_zero));

    if(bind(server_fd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0)
    {
      std::cout << "Bind failed\n";
      perror("bind");
      return false;
    }

    if (listen(server_fd, connection_backlog) != 0) {
      std::cerr << "listen failed\n";
      perror("listen");
      return false;
    }

    std::cout << "Listening on localhost " << port << " port" << std::endl;
    return true;
  }

  Client wait_for_client()
  {
    struct sockaddr_in client_addr;
    int client_addr_len = sizeof(client_addr);

    int client_fd = accept(server_fd, (struct sockaddr*)&client_addr, (socklen_t *) &client_addr_len);

    if(client_fd < 0)
    {
      std::cerr << "client accept failed..\n";
      perror("accept");
    }

    return {std::move(client_fd), std::move(client_addr)};
  }

  ~HttpListener() 
  {
    close(server_fd);
  }
private:
  int server_fd;
  struct sockaddr_in server_addr;
  bool server_running;
  int port;
  int connection_backlog;
};

struct HttpRequest
{
  std::string method {};
  std::string resource {};
  std::string protocol {};

  std::string hostname {};
  std::string user_agent {};

  std::string accept_types {};

  std::string headers {};
  std::string content_type {};
  std::string content_length {};

  std::string body {};
  bool invalid {false};

  void print()
  {
    std::cout << "Method: " << method << std::endl;
    std::cout << "Resource: " << resource << std::endl;
    std::cout << "Protocol: " << protocol << std::endl;
    std::cout << "Hostname: " << hostname << std::endl;
    std::cout << "UserAgent: " << user_agent << std::endl;
    std::cout << "Accept: " << accept_types << std::endl; 
    std::cout << "Headers: " << headers << std::endl;
    std::cout << "ContentType: " << content_type << std::endl;
    std::cout << "ContentLength: " << content_length << std::endl;
    std::cout << "Body: " << body << std::endl;
    std::cout << "Invalid: " << invalid << std::endl;
  }
};

class RequestParser{
public:
  RequestParser() {};

  int read_request(const Client& client)
  {
    memset(request_buff, '\0', MAX_REQUEST_LEN);
    int bytes_received = recv(client.fd, request_buff, MAX_REQUEST_LEN, 0);
    if(bytes_received == -1)
    {
      std::cerr << "Failed to read request from the client..";
      perror("recv");
    } 
    return bytes_received;
  }

  HttpRequest parse_request(const Client& client)
  {
    HttpRequest request;

    int bytes_received = read_request(client);
    if(bytes_received == -1)
    {
      request.invalid = true;
      return request;
    }

    std::istringstream iss {std::string(request_buff)};
    std::string line {}, temp {};
    int line_no = 0;
    
    std::cout << "DEBUG: request received ::\n";
    std::cout << request_buff << std::endl;

    bool body_started = false;
    while(std::getline(iss, line))
    {
      std::istringstream parse_line {line};
      if(line_no == 0) 
      {
        parse_line >> request.method;
        parse_line >> request.resource;
        parse_line >> request.protocol;
      }
      else if(line.find("Host:") != std::string::npos)
      {
        parse_line >> temp;
        parse_line >> request.hostname;
      }
      else if(line.find("User-Agent:") != std::string::npos)
      {
        parse_line >> temp;
        parse_line >> request.user_agent;
      }
      else if(line.find("Accept:") != std::string::npos)
      {
        parse_line >> temp;
        parse_line >> request.accept_types;
      }
      else if(line.find("Content-Type:") != std::string::npos)
      {
        parse_line >> temp;
        parse_line >> request.content_type;
      }
      else if(line.find("Content-Length:") != std::string::npos)
      {
        parse_line >> temp;
        parse_line >> request.content_length;
      }
      
      else if(body_started){
        if(!request.body.empty())
          request.body.append("\r\n");
        request.body.append(line);

        //request.body.push_back('\n');
      }
      else {
        std::cout << "Body started!!" << std::endl;
        std::cout << line << std::endl;
        body_started = true;
      }
      line_no += 1;
    }

    return request;
  }

static std::vector<std::string> split(const std::string& str, char c = '/')
{
  std::vector<std::string> split_result;
  
  std::string token;
  for(std::size_t i = 0; i < str.size(); ++i)
  {
    if(str[i] == c)
    {
        if(!token.empty())
            split_result.emplace_back(token);
        token.clear();
    }
    else {
        token.push_back(str[i]);
    }
  }
  
  if(!token.empty())
  {
    split_result.push_back(token);
  }

  return split_result;
}

private:
  char request_buff[MAX_REQUEST_LEN];
};

enum status_codes {
  RESP_OK, RESP_NOT_FOUND, POST_OK, RESP_SIZE
};

class RequestHandler
{
public:
  RequestHandler() {
    response_map[status_codes::RESP_OK].assign("HTTP/1.1 200 OK\r\n");
    response_map[status_codes::RESP_NOT_FOUND].assign("HTTP/1.1 404 Not Found\r\n\r\n");
    response_map[status_codes::POST_OK].assign("HTTP/1.1 201 Created\r\n\r\n");  
  }

  void handle_request(const Client& client) {
    char client_ip[INET_ADDRSTRLEN];
    int client_addr_len = sizeof(client.addr);
    int peer_name = getpeername(client.fd, (struct sockaddr*)&(client.addr),(socklen_t *) &client_addr_len);
    if(peer_name == -1)
    {
      std::cerr << "Failed to get peername\n";
      perror("getpeername");
      return;
    }
    inet_ntop(AF_INET, &peer_name, client_ip, INET_ADDRSTRLEN);
    std::cout << "Client connected:" << client_ip << "\n";

    auto request = parser.parse_request(client);
    request.print();
    if(request.invalid)
    {
      std::cerr << "Invalid request! or Failed to parse the request!";
      return;
    }

    auto resp = build_response(request);

    std::cout << "\n\nSending Response : \n";
    std::cout << resp << std::endl;

    int bytes_sent = send(client.fd, resp.c_str(), resp.length(), 0);
    if(bytes_sent == -1)
    {
      std::cerr << "Failed to send response to the client\n";
      perror("send");
    }

  }

  std::string build_response(const HttpRequest& request)
  {
    const std::string& rsrc = request.resource;
    auto split_result = parser.split(rsrc);
    if(split_result.empty())
    {
      //std::cout << "Empty resource requested.\n";
      return response_map[status_codes::RESP_OK] + "\r\n";
    }
    else {
      if(split_result[0] == "echo")
      {
        if(split_result.size() == 1)
          return response_map[status_codes::RESP_NOT_FOUND];
        auto resp = response_map[status_codes::RESP_OK];
        resp += "Content-Type: text/plain\r\nContent-Length: ";
        resp += std::to_string(split_result[1].size());
        resp.append("\r\n\r\n");
        resp.append(split_result[1]);

        return resp;
      }
      else if(split_result[0] == "user-agent")
      {
        auto resp = response_map[status_codes::RESP_OK];
        resp.append("Content-Type: text/plain\r\nContent-Length: ");
        resp.append(std::to_string(request.user_agent.length()));
        resp.append("\r\n\r\n");
        resp.append(request.user_agent);

        return resp;
      }
      else if(split_result[0] == "files")
      {
        if(request.method == "GET")
        {
          if(split_result.size() == 1)
            return response_map[status_codes::RESP_NOT_FOUND];
          
          std::string file_path {"/tmp/"};

          if(config.count("file_dir"))
            file_path = config["file_dir"];

          file_path.append(split_result[1]);
          struct stat buf;
          int result = stat(file_path.c_str(), &buf);
          if(result != 0) {
            perror("stat");

            return response_map[status_codes::RESP_NOT_FOUND];  
          }
          auto resp = response_map[status_codes::RESP_OK];
          resp.append("Content-Type: application/octet-stream\r\nContent-Length: ");
          resp.append(std::to_string(buf.st_size));
          resp.append("\r\n\r\n");
          std::ifstream file {file_path};
          std::string file_content {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
          resp.append(file_content);
          return resp;
        }
        else if(request.method == "POST")
        {
          if(split_result.size() == 1)
            return response_map[status_codes::RESP_NOT_FOUND];

          std::string file_path {"/tmp/"};

          if(config.count("file_dir"))
            file_path = config["file_dir"];

          file_path.append(split_result[1]);

          std::ofstream file(file_path, std::ios_base::trunc);
          file.write(request.body.c_str(), request.body.length());
          
          return response_map[status_codes::POST_OK];
        }
        else {
          return response_map[status_codes::RESP_NOT_FOUND];
        }
      }

      else {
        return response_map[status_codes::RESP_NOT_FOUND];
      }
    }
  }

  void set_config(std::string key, std::string val)
  {
    config[key] = val;
  }

private:
  RequestParser parser;
  std::string response_map[status_codes::RESP_SIZE];
  std::unordered_map<std::string, std::string> config;
};

void client_handler(Client client, std::string file_dir="/tmp/")
{
  RequestHandler request_handler;
  request_handler.set_config("file_dir", file_dir);
  request_handler.handle_request(client);
  client.disconnect();
}

int main(int argc, char **argv) {
  // Flush after every std::cout / std::cerr
  std::cout << std::unitbuf;
  std::cerr << std::unitbuf;
  
  std::string file_directory {"/tmp/"};

  if(argc == 3)
  {
    if(std::string(argv[1]).compare("--directory") == 0)
    {
      file_directory.assign(argv[2]);
      std::cout << "Serving directory: " << file_directory << std::endl;
    }
  }

  // You can use print statements as follows for debugging, they'll be visible when running tests.
  //std::cout << "Logs from your program will appear here!\n";

  HttpListener server(4221);

  while(true)
  {
    auto client = server.wait_for_client();
    std::thread c1(client_handler, std::move(client), file_directory);
    c1.detach();
  }

  return 0;
}
