/*
 * MARE Phase 11 fixture: setsid grandchild escapes the parent pgroup.
 * Compile inside container: gcc -o setsid_escape setsid_escape.c
 * Behavior:
 *   parent forks; child calls setsid() (creates new session, detaches pgroup)
 *   then sleeps 60s. Parent exits 0 immediately.
 *   Under strace -f + reap_followfork_strays, the grandchild MUST be SIGKILLed
 *   by reap_followfork_strays after the parent strace job terminates.
 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>

int main(void) {
    pid_t pid = fork();
    if (pid < 0) {
        perror("fork");
        return 1;
    }
    if (pid == 0) {
        /* child: detach into new session */
        if (setsid() < 0) {
            perror("setsid");
            _exit(2);
        }
        /* print our own pid so the test can read /proc/<pid> if it wants */
        fprintf(stdout, "escaped_pid=%d\n", (int)getpid());
        fflush(stdout);
        sleep(60);
        _exit(0);
    }
    /* parent exits immediately so the strace job terminates fast */
    return 0;
}
