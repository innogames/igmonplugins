BEGIN {
    mebibytes_warning = ARGV[1]
    if (mebibytes_warning !~ /^[0-9]+$/) {
        print "Usage: "ARGV[0] " -f check_deleted_files.awk <warning_threshold_MiB>"
        exit 3
    }

    M = 1048576
    cmd = "/usr/bin/lsof -n"
    while (cmd | getline line) {
        split(line, line_split)
        if (line_split[10] == "(deleted)") {
            total_waste += line_split[7]/M
            if (line_split[7] > mebibytes_warning*M) {
                message = message "\n" line_split[7]/M " MiB wasted by " line_split[9]
            }
        }
    }
    close(cmd)

    print total_waste " MiB wasted by deleted files" message
    if (total_waste > mebibytes_warning) {
        exit 1
    }
}
