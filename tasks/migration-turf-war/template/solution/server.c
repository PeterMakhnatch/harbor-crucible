#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static void respond(int client) {
    char request[1024];
    ssize_t size = recv(client, request, sizeof(request) - 1, 0);
    if (size <= 0) return;
    request[size] = '\0';
    const char *status = "200 OK";
    char body[128];
    if (strncmp(request, "GET /health ", 12) == 0) {
        snprintf(body, sizeof(body), "{\"lang\":\"typescript\",\"status\":\"ok\",\"version\":2}");
    } else if (strncmp(request, "GET /compute?x=", 15) == 0) {
        char *end;
        errno = 0;
        long long value = strtoll(request + 15, &end, 10);
        if (errno || end == request + 15 || (*end != ' ' && *end != '&') ||
            value < -3037000499LL || value > 3037000499LL) {
            status = "400 Bad Request";
            snprintf(body, sizeof(body), "{\"error\":\"x must be an integer\"}");
        } else {
            snprintf(body, sizeof(body), "{\"result\":%lld}", value * value);
        }
    } else {
        status = "404 Not Found";
        snprintf(body, sizeof(body), "{\"error\":\"not found\"}");
    }
    char response[384];
    int length = snprintf(response, sizeof(response),
        "HTTP/1.1 %s\r\nContent-Type: application/json\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n%s",
        status, strlen(body), body);
    send(client, response, length, MSG_NOSIGNAL);
}

int main(void) {
    int server = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in address = {.sin_family = AF_INET};
    address.sin_port = htons((unsigned short)atoi(getenv("PORT")));
    if (server < 0 || inet_pton(AF_INET, getenv("HOST"), &address.sin_addr) != 1 ||
        bind(server, (struct sockaddr *)&address, sizeof(address)) < 0 || listen(server, 8) < 0) return 1;
    for (;;) {
        int client = accept(server, NULL, NULL);
        if (client < 0) continue;
        respond(client);
        close(client);
    }
}
