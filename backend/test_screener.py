"""Test screener.in key ratios (top section)."""
import urllib.request, re

def fetch(symbol):
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    return urllib.request.urlopen(req, timeout=15).read().decode("utf-8")

html = fetch("RELIANCE")

# Top key ratios are in a ul.company-ratios section
ratios_ul = re.search(r'<ul[^>]*id="top-ratios"[^>]*>(.*?)</ul>', html, re.DOTALL)
if ratios_ul:
    items = re.findall(r'<li[^>]*>(.*?)</li>', ratios_ul.group(1), re.DOTALL)
    print("TOP RATIOS:")
    for item in items:
        name = re.search(r'<span[^>]*class="[^"]*name[^"]*"[^>]*>(.*?)</span>', item, re.DOTALL)
        val  = re.search(r'<span[^>]*class="[^"]*number[^"]*"[^>]*>(.*?)</span>', item, re.DOTALL)
        if name and val:
            n = re.sub(r'<[^>]+>', '', name.group(1)).strip()
            v = re.sub(r'<[^>]+>', '', val.group(1)).strip()
            print(f"  {n}: {v}")
else:
    # Try alternate structure
    print("No top-ratios ul found, trying alternate...")
    # Look for company-ratios
    cr = re.search(r'class="company-ratios"[^>]*>(.*?)</ul>', html, re.DOTALL)
    if cr:
        print("Found company-ratios:", cr.group(0)[:500])
    else:
        # Search for PE ratio directly
        pe_match = re.search(r'P/E.*?<span[^>]*>(\d+\.?\d*)</span>', html[:10000], re.DOTALL)
        print("PE match:", pe_match.group(1) if pe_match else "not found")
        # Print first 2000 chars to understand structure
        print(html[1000:3000])
