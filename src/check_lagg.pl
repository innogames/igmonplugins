#!/usr/bin/env perl
#
# InnoGames Monitoring Plugins - LAGG Check
#
# Copyright (c) 2017 InnoGames GmbH
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

use strict;

my (@output, @ports);
my (%states, %laggports, %laggproto, %laggportflag);
my ($current_if, $debug, $return, $msg);

$debug = 0;
@output = `ifconfig`;
$return = 0;

foreach (@output)
{
	# get current interface name, will be changed when we reach next int
	if (/^([\w]+): flags/ )
	{
		$current_if = $1;
	}
	# store the status of interface, current_if should already be set
	elsif ( /status: ([\w]+)$/ )
	{
		$states{$current_if} = $1;
	}
	#get the laggproto like failover or loadbalance
	elsif ( /laggproto ([\w]+)/ )
	{
		$laggproto{$current_if} = $1;
	}
	#add laggports to interface
	elsif ( /laggport: ([\w]+) flags=([\w]+)</ )
	{
		if (not $laggports{$current_if})
		{
			$laggports{$current_if} = [ ];
		}
		push (@{$laggports{$current_if}}, $1);
		$laggportflag{$1} = $2;
	}
}

# uncomment to check every interface and not only lagg members
#foreach ( keys(%states))
#{
#	if ($states{$_} ne 'active')
#	{
#		$msg += "$_ in state $states{$_}, ";
#		$return = 1;
#	}
#	print "Interface $_ is in state $states{$_}\n" if ($debug);
#}
foreach my $int ( keys(%laggproto))
{
	# sometimes we have preconfed laggs with no members
	if (exists($laggports{$int}))
	{
		@ports = @{$laggports{$int}};
	}

	if ( $states{$int} ne 'active' and !@ports)
	{
		$msg .= "$int is not active, ";
		$return = 1;
	}

	if ( $laggproto{$int} eq 'failover')
	{
		#all should be up and one should be in state 5
		print "$int is a failover lagg\n" if ($debug);
		my @temp; # array for flags of ints
		my %counts;
		foreach (@ports)
		{
			if ($states{$_} ne 'active')
			{
				$msg .= "member $_ of $int is not active, ";
				$return = 1;
			}
			push (@temp, $laggportflag{$_});
			print "member $_ of $int has state $states{$_} with flag $laggportflag{$_}\n" if ($debug);

		}
		$counts{$_}++ for @temp;
		if ( $counts{'5'} != 1 and !@ports)
		{
			$msg .= "Master interface is not Active for $int, ";
		}
		
	}
	elsif ($laggproto{$int} eq 'lacp')
	{
		#all ports should be up with correct flags
		foreach (@ports)
		{
			if ($states{$_} ne 'active')
			{
				$msg .= "member $_ of $int is not active, ";
				$return = 1;
			}
			if ($laggportflag{$_} ne '1c' )
			{
				$msg .= "member $_ of $int has wrong flag, ";
				$return = 1;
			}
			print "member $_ of $int has state $states{$_}\n" if ($debug);
		}

	}
	elsif ($laggproto{$int} eq 'loadbalance')
	{
		#all ports should be up
		print "$int is a loadbalance lagg\n" if ($debug);
		foreach (@ports)
		{
			if ($states{$_} ne 'active')
			{
				$msg .= "member $_ of $int is not active, ";
				$return = 1;
			}
			if ($laggportflag{$_} ne '4' )
			{
				$msg .= "member $_ of $int has wrong flag, ";
				$return = 1;
			}
			print "member $_ of $int has state $states{$_}\n" if ($debug);
		}
	}
}
if ($return)
{
	print "WARNING: " . $msg;
	exit $return;
} else {
	print "OK: No problems found\n";
}
