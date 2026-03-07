SESSION = "redacted"  # the api session cookie

AX_USER = "redacted"
AX_PASS = "redacted"
AX_API_KEY = "redacted"
AX_API_PREFIX = "http://ax:8000/v0"  # base url for ax api
AX_STATUS_ENDPOINT = f"{AX_API_PREFIX}/status"
AX_LOOKUP_ENDPOINT = f"{AX_API_PREFIX}/lookup"
AX_FIC_ENDPOINT = f"{AX_API_PREFIX}/fic"

ELASTICSEARCH_HOSTS: list[str] = ["http://elastic:espass@es:9200"]
