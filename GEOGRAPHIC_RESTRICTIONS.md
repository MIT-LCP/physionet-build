# Geographic Restrictions

This document explains how to configure geographic restrictions for published projects.

## Overview

PhysioNet supports geographic restrictions that prevent users from certain regions from accessing specific projects. This feature is useful for complying with legal or policy requirements.

**IMPORTANT NOTE: Geographic restrictions are only applied to projects where the `georestricted` flag is `True`. If `georestricted` is `False`, access will not be restricted.**

## Configuration

### Geolocation Database File

1. Get the GeoLite2-Country.mmdb.gz file from https://dev.maxmind.com/geoip/geolite2-free-geolocation-data/
2. Unzip it and make a note of the path (you'll need it for the `GEOIP_PATH` environment variable).

### Environment Variables

The blocked regions are configured using the `BLOCKED_REGIONS` environment variable:

```bash
# Default value (localhost for development/testing)
BLOCKED_REGIONS=localhost

# Custom configuration
BLOCKED_REGIONS=localhost,RU,CN,IR,NK

# Single region
BLOCKED_REGIONS=RU

# No regions blocked (empty)
BLOCKED_REGIONS=
```

The path to the folder containing GeoLite2-Country.mmdb file should be assigned to `GEOIP_PATH`:

```
GEOIP_PATH=path/to/folder/containing/file
```

### Format

- **Comma-separated**: Use commas to separate multiple region codes
- **ISO 3166-1 alpha-2**: Use standard two-letter region codes (e.g., RU for Russia, CN for China)
- **Special values**: `localhost` is supported for development and testing
- **Whitespace handling**: Leading and trailing whitespace is automatically removed
- **Case insensitive**: Region codes are case-insensitive

## Usage

### Setting Geographic Restrictions on Projects

1. Users from blocked regions will see the following message in the "Files" section of a project: "Data is not available in your region due to legal or policy restrictions."

### Testing

To test geographic restrictions:

1. Set the environment variable with test regions:
   ```bash
   export BLOCKED_REGIONS=localhost,US,CA
   ```

2. Access a georestricted project from localhost or a US/Canadian IP address
3. You should see the geographic restriction message

### Common Region Codes

- `localhost` - Local development environment
- `RU` - Russia
- `CN` - China
- `IR` - Iran
- `NK` - North Korea
- `US` - United States
- `CA` - Canada
- `MX` - Mexico
