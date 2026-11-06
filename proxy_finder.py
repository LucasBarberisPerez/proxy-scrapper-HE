
#!/usr/bin/env python3

import urllib.request
import urllib.error
import json
import socket
import time
from datetime import datetime
# Este script se ha creado utilizando inteligencia artifical - Chatgpt
# La finalidad de este script es según las indicaciones de los países que tenemos en COUNTRIES, encontrar un proxy candidato y con una cierta anonimidad, y con un tiempo minimo de disponibilidad. Hay que tener en cuenta que el repositorio que se usa se actualiza cada 5 minutos.

# Configuration
COUNTRIES = {
    "us": "United States",
    "ru": "Russia",
    "cn": "China"
}

PROTOCOL = "socks5"

# Anonymity levels
ANONYMITY_PRIORITY = {
    "elite": 2,
    "anonymous": 1,
    "transparent": 0
}

MIN_ANONYMITY_LEVEL = 1
MINIMUM_UPTIME = 50
TIMEOUT = 4

BASE_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "proxyscrape/free-proxy-list@main/"
    "proxies/countries/{country}/{protocol}/data.json"
)


def download_proxy_list(country):
    url = BASE_URL.format(
        country=country,
        protocol=PROTOCOL
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:

            data = response.read().decode("utf-8")
            return json.loads(data)

    except urllib.error.HTTPError as error:
        if error.code == 404:
            print("[!] No proxies available for this country.")
            return []

        print(f"[!] HTTP error: {error.code}")
        return []

    except Exception as error:
        print(f"[!] Download error: {error}")
        return []


def check_tcp_connection(ip, port):
    try:
        start_time = time.time()

        with socket.create_connection(
            (ip, port),
            timeout=TIMEOUT
        ):
            latency = (time.time() - start_time) * 1000

        return True, round(latency, 2)

    except OSError:
        return False, None


def get_proxy_score(proxy):
    anonymity = ANONYMITY_PRIORITY.get(
        proxy.get("anonymity", "").lower(),
        -1
    )

    uptime = proxy.get("uptime_percent") or 0

    latency = proxy.get("latency_ms")

    if latency is None:
        latency = 999999

    return (
        anonymity,
        uptime,
        -latency
    )


def find_proxy(country_code, country_name):
    print(f"\n[+] Searching for proxy in {country_name}...")

    candidates = download_proxy_list(country_code)

    # Filter by minimum anonymity and uptime
    candidates = [
        proxy for proxy in candidates
        if ANONYMITY_PRIORITY.get(
            proxy.get("anonymity", "").lower(),
            -1
        ) >= MIN_ANONYMITY_LEVEL
        and (proxy.get("uptime_percent") or 0)
        >= MINIMUM_UPTIME
    ]

    # Prioritize elite anonymity, uptime and latency
    candidates.sort(
        key=get_proxy_score,
        reverse=True
    )

    for proxy in candidates:

        ip = proxy.get("ip")
        port = proxy.get("port")

        if not ip or not port:
            continue

        print(f"    Testing {ip}:{port}")

        is_active, tcp_latency = check_tcp_connection(
            ip,
            int(port)
        )

        if is_active:
            proxy["tcp_latency_ms"] = tcp_latency
            proxy["requested_country"] = country_name

            print(
                f"[OK] Proxy found: "
                f"{ip}:{port}"
            )

            return proxy

    print(
        f"[!] No valid proxy found in {country_name}"
    )

    return None


def save_results(selected_proxies):

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Save detailed information
    with open(
        "selected_proxies.txt",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "SELECTED PROXIES - PROXYSCRAPE\n"
        )

        file.write(f"Date: {timestamp}\n")
        file.write("=" * 45 + "\n\n")

        for country_code, proxy in selected_proxies.items():

            file.write(
                f"COUNTRY: {COUNTRIES[country_code]}\n"
            )

            file.write(
                f"IP: {proxy['ip']}\n"
            )

            file.write(
                f"PORT: {proxy['port']}\n"
            )

            file.write(
                f"PROTOCOL: {PROTOCOL}\n"
            )

            file.write(
                f"ANONYMITY: {proxy.get('anonymity', 'N/A')}\n"
            )

            file.write(
                f"UPTIME: {proxy.get('uptime_percent', 'N/A')}%\n"
            )

            file.write(
                f"LATENCY: {proxy.get('latency_ms', 'N/A')} ms\n"
            )

            file.write(
                f"TCP LATENCY: {proxy.get('tcp_latency_ms', 'N/A')} ms\n"
            )

            file.write(
                f"ISP: {proxy.get('isp', 'N/A')}\n"
            )

            file.write(
                f"ASN: {proxy.get('asn', 'N/A')}\n"
            )

            file.write(
                f"LAST CHECKED: {proxy.get('last_checked', 'N/A')}\n"
            )

            file.write("-" * 45 + "\n\n")

    # Save Proxychains-compatible proxy list
    with open(
        "proxies.txt",
        "w",
        encoding="utf-8"
    ) as file:

        for country_code in ("us", "ru", "cn"):

            if country_code in selected_proxies:

                proxy = selected_proxies[country_code]

                file.write(
                    f"socks5 {proxy['ip']} "
                    f"{proxy['port']}\n"
                )

    # Save Proxychains configuration snippet
    with open(
        "proxychains_config.txt",
        "w",
        encoding="utf-8"
    ) as file:

        file.write("# Proxychains4 configuration snippet\n")
        file.write("# Copy and paste this into your existing configuration\n\n")

        file.write("strict_chain\n")
        file.write("proxy_dns\n\n")
        file.write("[ProxyList]\n")

        for country_code in ("us", "ru", "cn"):

            if country_code in selected_proxies:

                proxy = selected_proxies[country_code]

                file.write(
                    f"socks5 {proxy['ip']} "
                    f"{proxy['port']} "
                    f"# {COUNTRIES[country_code]}\n"
                )

    # Save complete metadata
    with open(
        "selected_proxies.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            selected_proxies,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("\n[+] Files generated:")
    print("    selected_proxies.txt")
    print("    proxies.txt")
    print("    proxychains_config.txt")
    print("    selected_proxies.json")


def main():

    selected_proxies = {}

    print("=" * 45)
    print(" SOCKS5 PROXY FINDER")
    print(" Minimum anonymity: anonymous")
    print("=" * 45)

    for country_code, country_name in COUNTRIES.items():

        proxy = find_proxy(
            country_code,
            country_name
        )

        if proxy:
            selected_proxies[country_code] = proxy

    print("\n========== SUMMARY ==========\n")

    for country_code, country_name in COUNTRIES.items():

        if country_code in selected_proxies:

            proxy = selected_proxies[country_code]

            print(
                f"[OK] {country_name}: "
                f"{proxy['ip']}:{proxy['port']} "
                f"({proxy['anonymity']})"
            )

        else:

            print(
                f"[UNAVAILABLE] {country_name}"
            )

    if selected_proxies:
        save_results(selected_proxies)

    if len(selected_proxies) < 3:

        print(
            "\n[!] Proxies were not found "
            "for all requested countries."
        )

        print(
            "[!] Files contain only "
            "the available proxies."
        )

    else:

        print(
            "\n[+] One proxy from each country "
            "was successfully selected."
        )


if __name__ == "__main__":
    main()
