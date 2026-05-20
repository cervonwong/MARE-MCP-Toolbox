/*
 * MARE Phase 11 fixture: confirms netns wraps block DNS resolution.
 * Compile inside container: gcc -o dns_lookup dns_lookup.c
 * Expected behavior under run_strace + per-call unshare --net:
 *   getaddrinfo() returns ENETUNREACH (or EAI_AGAIN / EAI_FAIL with ENETUNREACH in errno).
 * Without the unshare wrap (negative control): resolves successfully.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <netdb.h>
#include <sys/socket.h>

int main(void) {
    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    int rc = getaddrinfo("example.com", "80", &hints, &res);
    if (rc != 0) {
        fprintf(stderr, "getaddrinfo failed: %s (errno=%d)\n", gai_strerror(rc), errno);
        return 2;
    }
    if (res) {
        fprintf(stdout, "resolved example.com OK\n");
        freeaddrinfo(res);
    }
    return 0;
}
