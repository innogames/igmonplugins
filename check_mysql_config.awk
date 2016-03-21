BEGIN {
	outfile="/tmp/check_mysql_config"
	exitcode = 0
	diffcmd = "pt-config-diff h=localhost --user=" ENVIRON["MYSQL_USER"] " --password=" ENVIRON["MYSQL_PASSWORD"] " --noreport --noversion-check --ignore-variables=wsrep_sst_auth"
	if (ARGC<3) {
		print "Give me at least two files!" > "/dev/stderr"
		exitcode = 3
		exit
	}
	if ( ! ENVIRON["MYSQL_USER"] || ! ENVIRON["MYSQL_PASSWORD"] ) {
		print "Please specify MySQL username and password as MYSQL_USER and MYSQL_PASSWORD environment variables." > "/dev/stderr"
		exitcode = 3
		exit
	}
	if ( ENVIRON["DEBUG"] ) {
		debug = 1
	}
	print > outfile
}

{
	if ( /\[mysqld\]/ ) {
		mysqld_section[FILENAME]="yes"
	}

	if (FNR!=NR && ! /^(\[|!|#|$)/) {
		confd_params[$1]=confd_params[$1]" "FILENAME;
	}
}

END {
	if (exitcode != 0) {
		exit exitcode
	}

	while (getline < ARGV[1]) {
		if ( /^(#|$)/ ) {
			# Skip comment lines
		} else if ($1 in confd_params) {
			if ( debug ) print "Parameter "$1" redefined in: " confd_params[$1] > "/dev/stderr"
		} else {
			print $0 >> outfile
		}
	}

	if ( debug ) print "Comparing file " outfile > /dev/stderr
	system(diffcmd " " outfile)

	for (arg=2; arg<ARGC; arg++) {
		filename = ARGV[arg]
		if (filename in mysqld_section) {
			if ( debug ) print "Comparing file " filename > "/dev/stderr"
			out = system(diffcmd " " filename)
			if ( out != 0) {
				exitcode = 1
				bad_files = bad_files" "filename
			}
		}
	}

	if (exitcode == 0) {
		print "All variables are fine."
	} else {
		print "Some variables are different, call the commands from below to see the difference:"
		split(bad_files, bad_files_array)
		for (bad_file in bad_files_array) {
			print "pt-config-diff h=localhost " bad_files_array[bad_file]
		}
	}

	exit exitcode
}

