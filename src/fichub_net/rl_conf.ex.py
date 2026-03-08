# Determines whether the fichub.limiter table will be used in general to rate
# limit based on actual request rate.
DYNAMIC_RATE_LIMIT = True

# Configuration for static rate limiting (not based on actual request rate).
# In general this looks like:
#   1 + (rand() * base) + extra  # noqa: ERA001

# A static set of pre-determined remotes which should have a given base delay.
# If the remote is not in here nor the NO_LIMIT_UPSTREAMS it will be defaulted
# to 0.1.
LIMIT_UPSTREAMS: dict[str, float] = {}
# A static set of pre-determined remotes which should have an extra delay
# applied to every request.
LIMIT_UPSTREAMS_EXTRA: dict[str, float] = {}
# IPs which should have no static rate limiting applied. We also treat these
# as "authorized" for the datacenter check.
NO_LIMIT_UPSTREAMS: set[str] = set()

# Types of ip tags to load, if one cannot be parsed the service will not start up.
# If there are files in dat/ that are not covered here an error will also be raised.
# source path => (type, tag)
IP_TAG_SOURCES: dict[str, tuple[str, str]] = {
    "dat/.gitkeep": ("ignore", "ignore"),
}


# An extra set of remotes to treat as "weird" and handle similarly to
# datacenter IPs.
WEIRD_UPSTREAMS: set[str] = set()
