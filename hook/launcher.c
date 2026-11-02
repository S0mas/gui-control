#define _GNU_SOURCE

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define MAX_ARGS 256
#define MAX_CMDLINE 65536

static int read_cmdline(char *buffer, size_t size, char **argv, int max_args)
{
    FILE *file = fopen("/proc/self/cmdline", "rb");
    if (!file)
    {
        return -1;
    }

    size_t length = fread(buffer, 1, size - 1, file);
    fclose(file);
    if (length == 0)
    {
        return -1;
    }
    buffer[length] = '\0';

    int count = 0;
    for (size_t offset = 0; offset < length && count < max_args - 1;)
    {
        argv[count++] = buffer + offset;
        offset += strlen(buffer + offset) + 1;
    }
    argv[count] = NULL;
    return count;
}

int main(int argc, char **argv)
{
    const char *target = getenv("GUI_CONTROL_TARGET");
    const char *hook = getenv("GUI_CONTROL_LIB");

    if (!target || target[0] == '\0')
    {
        fprintf(stderr, "gui-control-launch: GUI_CONTROL_TARGET is not set\n");
        return 2;
    }

    if (hook && hook[0] != '\0')
    {
        const char *existing = getenv("LD_PRELOAD");
        if (existing && existing[0] != '\0')
        {
            char combined[8192];
            snprintf(combined, sizeof(combined), "%s:%s", hook, existing);
            setenv("LD_PRELOAD", combined, 1);
        }
        else
        {
            setenv("LD_PRELOAD", hook, 1);
        }
    }

    char buffer[MAX_CMDLINE];
    char *full[MAX_ARGS];
    const int count = read_cmdline(buffer, sizeof(buffer), full, MAX_ARGS);

    char self[4096];
    const ssize_t self_length = readlink("/proc/self/exe", self, sizeof(self) - 1);
    if (self_length > 0)
    {
        self[self_length] = '\0';
    }
    else
    {
        self[0] = '\0';
    }

    if (count > 0)
    {
        for (int index = 0; index < count; ++index)
        {
            if (strcmp(full[index], argv[0]) == 0
                || (self[0] != '\0' && strcmp(full[index], self) == 0))
            {
                full[index] = (char *) target;
                execv(full[0], full);
                fprintf(stderr, "gui-control-launch: exec '%s' failed: %s\n", full[0], strerror(errno));
                return 127;
            }
        }
    }

    argv[0] = (char *) target;
    execv(target, argv);
    fprintf(stderr, "gui-control-launch: exec '%s' failed: %s\n", target, strerror(errno));
    return 127;
}
