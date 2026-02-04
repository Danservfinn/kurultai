import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "authentik.root.settings")
import django
django.setup()

from authentik.outposts.models import Outpost
from authentik.providers.proxy.models import ProxyProvider

# Get the embedded outpost
embedded = Outpost.objects.filter(managed="goauthentik.io/outposts/embedded").first()
print(f"Embedded Outpost: {embedded}")

if embedded:
    # Get our proxy provider
    proxy = ProxyProvider.objects.filter(name="OpenClaw Proxy Provider").first()
    print(f"Proxy Provider: {proxy}")
    
    if proxy:
        # Add the proxy provider to the embedded outpost
        embedded.providers.add(proxy)
        embedded.save()
        print(f"Added {proxy.name} to {embedded.name}")
        print(f"Outpost providers: {list(embedded.providers.all())}")
    else:
        print("ERROR: OpenClaw Proxy Provider not found")
else:
    print("ERROR: Embedded outpost not found")
