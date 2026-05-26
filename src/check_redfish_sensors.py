#!/usr/bin/env python3
"""InnoGames Monitoring Plugins - Redfish Sensors Check

This script queries the BMC of a Supermicro or Dell server via the Redfish
HTTP API and reports the health of all sensors as well as power and thermal
redundancies.

Copyright (c) 2026 InnoGames GmbH
"""
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

import argparse
import signal
import sys

import requests
import urllib3


class ExitCodes:
    ok = 0
    warning = 1
    critical = 2
    unknown = 3


TAG_TO_EXIT = {
    '[OK]': ExitCodes.ok,
    '[WARN]': ExitCodes.warning,
    '[CRIT]': ExitCodes.critical,
    '[UNK]': ExitCodes.unknown,
}

# Characters that would break Nagios perfdata parsing inside a label. The
# label is single-quoted, but quote, equals, semicolon, pipe, and any
# whitespace can still confuse downstream parsers.
PERFDATA_LABEL_BAD_CHARS = str.maketrans({
    "'": '_',
    '=': '_',
    ';': '_',
    '|': '_',
    ' ': '_',
    '\t': '_',
    '\n': '_',
    '\r': '_',
})


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            'Check Redfish sensors and power/thermal redundancies on '
            'Supermicro and Dell servers.'
        ),
    )
    parser.add_argument(
        '--hostname',
        required=True,
        help='Hostname or IP of the BMC to query.',
    )
    parser.add_argument(
        '--username',
        required=True,
        help='Redfish username.',
    )
    parser.add_argument(
        '--password',
        required=True,
        help='Redfish password.',
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=5.0,
        help='HTTP request timeout in seconds (default: 5).',
    )
    parser.add_argument(
        '--insecure',
        action='store_true',
        help='Ignore invalid BMC TLS certificate.',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    redfish_client = RedfishClient(
        hostname=args.hostname,
        username=args.username,
        password=args.password,
        timeout=args.timeout,
        verify_ssl=not args.insecure,
    )

    def handle_sigterm(_signum, _frame):
        redfish_client.logout()
        print('UNKNOWN: terminated by signal')
        sys.exit(ExitCodes.unknown)

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        redfish_client.login()
        chassis_list = redfish_client.get_collection_members(
            '/redfish/v1/Chassis',
        ) or []
        members_data = []
        for chassis in chassis_list:
            members_data.append(get_chassis_data(redfish_client, chassis))

        if not members_data:
            print('UNKNOWN: No chassis found via Redfish')
            sys.exit(ExitCodes.unknown)

        code = overall_exit_code(members_data)
        output = build_output(members_data, code)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else '?'
        if status in (401, 403):
            output = f'UNKNOWN: Authentication failed ({status}) for {args.hostname}'
        else:
            output = f'UNKNOWN: HTTP error {status} from {args.hostname}: {e}'
        code = ExitCodes.unknown
    except requests.RequestException as e:
        output = f'UNKNOWN: Unable to query {args.hostname} via Redfish: {e}'
        code = ExitCodes.unknown
    finally:
        redfish_client.logout()

    print(output)
    sys.exit(code)


def get_chassis_data(redfish_client, chassis):
    sensors = []
    sensors_ref = chassis.get('Sensors', {}).get('@odata.id')
    if sensors_ref:
        for sensor in redfish_client.get_collection_members(
                sensors_ref) or []:
            state = sensor.get('Status', {}).get('State')
            if state is not None and state not in ('Enabled', 'Quiesced'):
                continue
            sensors.append(sensor)

    redundancies = []
    thermal_ref = chassis.get('ThermalSubsystem', {}).get('@odata.id')
    if thermal_ref:
        thermal = redfish_client.get_optional(thermal_ref)
        if thermal:
            for red in thermal.get('FanRedundancy', []):
                redundancies.append({
                    'name': red.get('Name', 'Fan Redundancy'),
                    'mode': red.get('RedundancyType', 'Unknown'),
                    'status': red.get('Status', {}),
                })

    power_ref = chassis.get('PowerSubsystem', {}).get('@odata.id')
    if power_ref:
        power = redfish_client.get_optional(power_ref)
        if power:
            for red in power.get('PowerSupplyRedundancy', []):
                redundancies.append({
                    'name': red.get('Name', 'Power Supply Redundancy'),
                    'mode': red.get('RedundancyType', 'Unknown'),
                    'status': red.get('Status', {}),
                })

    return (chassis, sensors, redundancies)


def health_tag(status):
    if not status:
        return '[OK]'
    for key in ('Health', 'HealthRollup'):
        value = status.get(key)
        if value is None:
            continue
        value = value.lower()
        if value == 'critical':
            return '[CRIT]'
        if value == 'warning':
            return '[WARN]'
    return '[OK]'


def reading_tag(sensor):
    """Classify a sensor reading against its thresholds."""
    raw = sensor.get('Reading')
    if raw is None:
        return '[OK]'

    try:
        reading = float(raw)
    except (TypeError, ValueError):
        return '[OK]'

    thresholds = sensor.get('Thresholds', {})
    upper_crit = thresholds.get('UpperCritical', {}).get('Reading')
    upper_warn = thresholds.get('UpperCaution', {}).get('Reading')
    lower_crit = thresholds.get('LowerCritical', {}).get('Reading')
    lower_warn = thresholds.get('LowerCaution', {}).get('Reading')

    if upper_crit is not None and reading >= upper_crit:
        return '[CRIT]'
    if lower_crit is not None and reading <= lower_crit:
        return '[CRIT]'
    if upper_warn is not None and reading >= upper_warn:
        return '[WARN]'
    if lower_warn is not None and reading <= lower_warn:
        return '[WARN]'
    return '[OK]'


def format_threshold(value):
    """Render thresholds like Nagios perfdata: integer floats lose .0."""
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def format_member_header(chassis):
    parts = []
    name_parts = []
    for key in ('Manufacturer', 'Model'):
        val = chassis.get(key, '')
        if val:
            name_parts.append(val.strip())
    if name_parts:
        parts.append(' '.join(name_parts))

    for key, label in (
            ('PowerState', 'Power'),
            ('IndicatorLED', 'LED'),
            ('SKU', 'SKU'),
            ('SerialNumber', 'SerNo'),
            ('PartNumber', 'PartNumber'),
    ):
        val = chassis.get(key)
        if val:
            parts.append(f'{label}: {val}')

    health = chassis.get('Status', {}).get('Health')
    if health:
        parts.append(f'Health: {health}')

    return 'Member: ' + ', '.join(parts)


def format_table(headers, rows):
    """Render a table using the ' ! ' / '-+-' style from the spec."""
    widths = []
    for i, header in enumerate(headers):
        width = len(header)
        for row in rows:
            if i < len(row):
                width = max(width, len(str(row[i])))
        widths.append(width)

    last = len(widths) - 1

    def render(cells):
        # Don't pad the last cell — keeps rows free of trailing whitespace.
        return ' ! '.join(
            str(c).ljust(w) if i != last else str(c)
            for i, (c, w) in enumerate(zip(cells, widths))
        )

    sep_segments = []
    for i, w in enumerate(widths):
        # First column has no leading space, last has no trailing space.
        # Inner columns get a leading and trailing space pulled into the dashes.
        extra = 1 if i in (0, len(widths) - 1) else 2
        sep_segments.append('-' * (w + extra))

    return '\n'.join(
        [render(headers), '+'.join(sep_segments)] + [render(r) for r in rows]
    )


def sanitize_perfdata_label(label):
    """Return a Nagios-safe perfdata label.

    Replaces characters that break perfdata parsing with underscores,
    collapses repeated underscores, and trims leading/trailing ones.
    Falls back to 'sensor' if the result is empty.
    """
    sanitized = label.translate(PERFDATA_LABEL_BAD_CHARS)
    while '__' in sanitized:
        sanitized = sanitized.replace('__', '_')
    return sanitized.strip('_') or 'sensor'


def perfdata_for_sensor(sensor):
    reading = sensor.get('Reading')
    if reading is None:
        return None

    location = sensor.get('PhysicalContext', 'Unknown')
    name = sensor.get('Name') or sensor.get('Id') or 'sensor'
    label = sanitize_perfdata_label(f'{location}_{name}')

    # Any unit other than % is replaced with an empty string as Nagios perfdata
    # can only handle a very specific set of units.
    perf_unit = '%' if sensor.get('ReadingUnits') == '%' else ''

    thresholds = sensor.get('Thresholds', {})
    upper_warn = thresholds.get('UpperCaution', {}).get('Reading')
    upper_crit = thresholds.get('UpperCritical', {}).get('Reading')

    value_part = f'{reading}{perf_unit}'

    if upper_warn is None and upper_crit is None:
        return f"'{label}'={value_part}"
    if upper_crit is None:
        return f"'{label}'={value_part};{format_threshold(upper_warn)}"
    if upper_warn is None:
        return f"'{label}'={value_part};;{format_threshold(upper_crit)}"
    return (
        f"'{label}'={value_part};"
        f"{format_threshold(upper_warn)};{format_threshold(upper_crit)}"
    )


def sensor_table(sensors):
    rows = []
    for sensor in sensors:
        rows.append([
            sensor.get('Name') or sensor.get('Id') or 'sensor',
            sensor.get('PhysicalContext', ''),
            str(sensor.get('Reading', '')),
            sensor.get('ReadingUnits', ''),
            reading_tag(sensor),
            health_tag(sensor.get('Status', {})),
        ])
    return format_table(
        ['Sensor', 'Location', 'Reading', 'Unit', 'Value', 'Health'], rows,
    )


def redundancy_table(redundancies):
    rows = []
    for redundancy in redundancies:
        rows.append([
            redundancy['name'],
            redundancy['mode'],
            health_tag(redundancy['status']),
        ])
    return format_table(['Redundancy', 'Mode', 'Health'], rows)


def format_member_section(chassis, sensors, redundancies):
    lines = [format_member_header(chassis)]
    if sensors:
        lines.append('')
        lines.append(sensor_table(sensors))
    if redundancies:
        # Two blank lines between sensor and redundancy tables, one blank
        # line if the member has no sensor table.
        lines.append('')
        if sensors:
            lines.append('')
        lines.append(redundancy_table(redundancies))
    return '\n'.join(lines)


def overall_exit_code(members_data):
    worst = ExitCodes.ok
    for chassis, sensors, redundancies in members_data:
        worst = max(worst, TAG_TO_EXIT[health_tag(chassis.get('Status', {}))])
        for sensor in sensors:
            worst = max(
                worst,
                TAG_TO_EXIT[reading_tag(sensor)],
                TAG_TO_EXIT[health_tag(sensor.get('Status', {}))],
            )
        for r in redundancies:
            worst = max(worst, TAG_TO_EXIT[health_tag(r['status'])])
    return worst


def build_summary(exit_code, member_count):
    if exit_code == ExitCodes.ok:
        return f'OK: no issues found, checked sensors on {member_count} members.'
    if exit_code == ExitCodes.warning:
        return f'WARNING: sensor issues found, checked {member_count} members.'
    if exit_code == ExitCodes.critical:
        return f'CRITICAL: sensor issues found, checked {member_count} members.'
    return f'UNKNOWN: unable to assess sensors on {member_count} members.'


def build_output(members_data, exit_code):
    summary = build_summary(exit_code, len(members_data))

    sections = [
        format_member_section(chassis, sensors, redundancies)
        for chassis, sensors, redundancies in members_data
    ]
    body = '\n\n\n'.join(sections)

    perfdata = []
    for _, sensors, _ in members_data:
        for s in sensors:
            entry = perfdata_for_sensor(s)
            if entry:
                perfdata.append(entry)

    output = summary + '\n\n' + body if body else summary
    if perfdata:
        output += '|' + ' '.join(perfdata)
    return output


class RedfishClient:
    def __init__(self, hostname, username, password, timeout, verify_ssl):
        self.base_url = f'https://{hostname}'
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/json'})
        self.session.verify = verify_ssl
        self.timeout = timeout
        self._session_url = None
        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def login(self):
        """Open a Redfish session and switch the client over to X-Auth-Token."""
        url = self.base_url + '/redfish/v1/SessionService/Sessions'
        response = self.session.post(
            url,
            json={'UserName': self.username, 'Password': self.password},
            timeout=self.timeout,
        )
        response.raise_for_status()
        token = response.headers.get('X-Auth-Token')
        location = response.headers.get('Location')
        if not token or not location:
            raise requests.RequestException(
                'Redfish login response missing X-Auth-Token or Location header'
            )
        self.session.headers['X-Auth-Token'] = token
        # Location may come back relative or absolute.
        self._session_url = (
            location if location.startswith('http')
            else self.base_url + location
        )

    def logout(self):
        """Close the Redfish session. Idempotent; safe to call from signal
        handlers and finally clauses."""
        url = self._session_url
        if not url:
            return
        # Clear first so re-entry (signal handler racing finally clause) is a no-op.
        self._session_url = None
        try:
            self.session.delete(url, timeout=self.timeout)
        except requests.RequestException:
            pass
        self.session.headers.pop('X-Auth-Token', None)

    def get(self, path):
        url = path if path.startswith('http') else self.base_url + path
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_optional(self, path):
        """Same as get(), but returns None on HTTP 404."""
        try:
            return self.get(path)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    def get_collection_members(self, path):
        """Return full member objects from a Redfish collection.

        Requests the collection with ?$expand=.($levels=1) so each member
        is inlined in a single response. Falls back to per-member GETs on
        BMCs that reject the query parameter or silently ignore it.
        Returns None when the collection itself responds with HTTP 404.
        """
        sep = '&' if '?' in path else '?'
        expanded_path = f'{path}{sep}$expand=.($levels=1)'
        try:
            collection = self.get(expanded_path)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 404:
                return None
            if status is not None and 400 <= status < 500:
                collection = self.get_optional(path)
                if collection is None:
                    return None
            else:
                raise

        members = []
        for member in collection.get('Members', []):
            # When $expand worked, members carry their full payload inline
            # (Name, Reading, Status, ...). When it was ignored, they only
            # carry @odata.* metadata and must be fetched individually.
            if any(not k.startswith('@odata.') for k in member):
                members.append(member)
                continue
            link = member.get('@odata.id')
            if link:
                members.append(self.get(link))
        return members


if __name__ == '__main__':
    main()
