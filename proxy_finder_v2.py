#!/usr/bin/env python3
"""
SOCKS5 PROXY FINDER (v2)

Cambios respecto a la versión anterior:
  - Verifica cada proxy con tráfico REAL (curl a través del proxy), no solo
    con una conexión TCP. Así se detectan los proxies que responden pero
    deniegan el tráfico ("denied").
  - Comprueba la IP de salida y, opcionalmente, que el país coincide.
  - Prueba los candidatos en paralelo (mucho más rápido).
  - Guarda varios candidatos verificados por país (recambios).
  - Prueba la cadena completa con proxychains4 y busca una combinación
    que funcione de verdad.
  - Genera dos configuraciones: strict (la combinación verificada) y
    dynamic (todos los candidatos, salta los que fallen).

Requisitos: python3, curl y (opcional, para probar la cadena) proxychains4.
"""

import itertools
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ----------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------
COUNTRIES = {
    "us": "United States",
    "ru": "Russia",
    "cn": "China",
}

PROTOCOL = "socks5"

ANONYMITY_PRIORITY = {"elite": 2, "anonymous": 1, "transparent": 0}
MIN_ANONYMITY_LEVEL = 1       # 1 = anonymous o superior
MINIMUM_UPTIME = 50           # % mínimo según el repositorio

TIMEOUT = 10                  # segundos por prueba de proxy (los gratuitos son lentos)
MAX_CANDIDATES_TO_TEST = 40   # cuántos candidatos probar como máximo por país
WORKERS = 20                  # pruebas en paralelo
KEEP_PER_COUNTRY = 3          # proxies verificados a guardar por país
STRICT_COUNTRY_CHECK = True   # exigir que la IP de salida sea del país buscado

CHAIN_TIMEOUT = 40            # segundos para probar la cadena completa
MAX_CHAIN_COMBOS = 12         # combinaciones máximas a probar con proxychains
TEST_CHAIN = True             # probar la cadena con proxychains4 si está instalado

# La salida de ipinfo devuelve ip y país; ifconfig.me es el respaldo.
TEST_URLS = ["https://ipinfo.io/json", "https://ifconfig.me/ip"]

BASE_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "proxyscrape/free-proxy-list@main/"
    "proxies/countries/{country}/{protocol}/data.json"
)


# ----------------------------------------------------------------------
# Descarga y filtrado
# ----------------------------------------------------------------------
def download_proxy_list(country):
    url = BASE_URL.format(country=country, protocol=PROTOCOL)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            print("[!] No proxies available for this country.")
        else:
            print(f"[!] HTTP error: {error.code}")
        return []
    except Exception as error:
        print(f"[!] Download error: {error}")
        return []


def get_proxy_score(proxy):
    anonymity = ANONYMITY_PRIORITY.get(proxy.get("anonymity", "").lower(), -1)
    uptime = proxy.get("uptime_percent") or 0
    latency = proxy.get("latency_ms")
    if latency is None:
        latency = 999999
    return (anonymity, uptime, -latency)


def filter_candidates(candidates):
    filtered = [
        p for p in candidates
        if p.get("ip") and p.get("port")
        and ANONYMITY_PRIORITY.get(p.get("anonymity", "").lower(), -1) >= MIN_ANONYMITY_LEVEL
        and (p.get("uptime_percent") or 0) >= MINIMUM_UPTIME
    ]
    filtered.sort(key=get_proxy_score, reverse=True)
    return filtered


# ----------------------------------------------------------------------
# Verificación real del proxy
# ----------------------------------------------------------------------
def check_socks5_proxy(ip, port, country_code):
    """
    Hace una petición real a través del proxy con curl.
    Devuelve un dict con IP/país de salida y latencia, o None si falla.
    """
    for url in TEST_URLS:
        start = time.time()
        try:
            result = subprocess.run(
                [
                    "curl", "-s",
                    "--max-time", str(TIMEOUT),
                    "--socks5-hostname", f"{ip}:{port}",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=TIMEOUT + 3,
            )
        except subprocess.TimeoutExpired:
            continue

        output = result.stdout.strip()
        if result.returncode != 0 or not output:
            continue

        latency = round((time.time() - start) * 1000, 2)
        exit_ip, exit_country = None, None

        if url.endswith("/json"):
            try:
                data = json.loads(output)
                exit_ip = data.get("ip")
                exit_country = (data.get("country") or "").lower()
            except json.JSONDecodeError:
                continue  # respuesta que no es JSON: proxy que manipula tráfico
        else:
            exit_ip = output.splitlines()[0]

        if not exit_ip:
            continue

        # Si tenemos país de salida, validarlo
        if STRICT_COUNTRY_CHECK and exit_country and exit_country != country_code:
            return None

        return {
            "exit_ip": exit_ip,
            "exit_country": exit_country or "unknown",
            "tcp_latency_ms": latency,   # latencia real de la petición completa
        }

    return None


def find_proxies(country_code, country_name):
    print(f"\n[+] Searching for proxies in {country_name}...")

    candidates = filter_candidates(download_proxy_list(country_code))
    candidates = candidates[:MAX_CANDIDATES_TO_TEST]

    if not candidates:
        print(f"[!] No candidates after filtering in {country_name}")
        return []

    print(f"    Testing {len(candidates)} candidates with real traffic...")

    verified = []

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(check_socks5_proxy, p["ip"], int(p["port"]), country_code): p
            for p in candidates
        }
        for future in as_completed(futures):
            proxy = futures[future]
            try:
                info = future.result()
            except Exception:
                info = None

            if info:
                proxy.update(info)
                proxy["requested_country"] = country_name
                verified.append(proxy)
                print(f"    [OK] {proxy['ip']}:{proxy['port']} "
                      f"-> exit {info['exit_ip']} ({info['exit_country']}) "
                      f"{info['tcp_latency_ms']} ms")

    # Los mejores primero: anonimato, uptime y latencia real medida
    verified.sort(
        key=lambda p: (
            ANONYMITY_PRIORITY.get(p.get("anonymity", "").lower(), -1),
            p.get("uptime_percent") or 0,
            -p["tcp_latency_ms"],
        ),
        reverse=True,
    )

    verified = verified[:KEEP_PER_COUNTRY]

    if not verified:
        print(f"[!] No valid proxy found in {country_name}")
    else:
        print(f"[+] {len(verified)} verified proxies kept for {country_name}")

    return verified


# ----------------------------------------------------------------------
# Prueba de la cadena completa
# ----------------------------------------------------------------------
def build_config(chain_mode, proxies, with_comments=True):
    lines = [
        chain_mode,
        "proxy_dns",
        "tcp_read_time_out 15000",
        "tcp_connect_time_out 8000",
        "",
        "[ProxyList]",
    ]
    for code, proxy in proxies:
        comment = f" # {COUNTRIES[code]}" if with_comments else ""
        lines.append(f"socks5 {proxy['ip']} {proxy['port']}{comment}")
    return "\n".join(lines) + "\n"


def test_chain(combo):
    """combo = [(code, proxy), ...] en orden. Devuelve la IP de salida o None."""
    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as tmp:
        tmp.write(build_config("strict_chain", combo, with_comments=False))
        conf_path = tmp.name

    try:
        result = subprocess.run(
            [
                "proxychains4", "-q", "-f", conf_path,
                "curl", "-s", "--max-time", str(CHAIN_TIMEOUT - 5),
                "https://ifconfig.me/ip",
            ],
            capture_output=True,
            text=True,
            timeout=CHAIN_TIMEOUT,
        )
        output = result.stdout.strip()
        if result.returncode == 0 and output:
            return output.splitlines()[0]
    except subprocess.TimeoutExpired:
        pass
    finally:
        os.unlink(conf_path)

    return None


def find_working_chain(verified_by_country):
    """Prueba combinaciones (un proxy por país) hasta encontrar una cadena válida."""
    codes = [c for c in COUNTRIES if verified_by_country.get(c)]
    if len(codes) < 2:
        return None, None

    combos = itertools.product(*[verified_by_country[c] for c in codes])

    for i, combo in enumerate(combos, start=1):
        if i > MAX_CHAIN_COMBOS:
            break
        chain = list(zip(codes, combo))
        label = " -> ".join(f"{p['ip']}:{p['port']}" for _, p in chain)
        print(f"    [{i}] Testing chain: {label}")
        exit_ip = test_chain(chain)
        if exit_ip:
            print(f"    [OK] Chain works, exit IP: {exit_ip}")
            return chain, exit_ip

    return None, None


# ----------------------------------------------------------------------
# Guardado de resultados
# ----------------------------------------------------------------------
def save_results(verified_by_country, working_chain, chain_exit_ip):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Informe detallado
    with open("selected_proxies.txt", "w", encoding="utf-8") as f:
        f.write("SELECTED PROXIES - PROXYSCRAPE\n")
        f.write(f"Date: {timestamp}\n")
        f.write("=" * 45 + "\n\n")

        for code, proxies in verified_by_country.items():
            for n, proxy in enumerate(proxies, start=1):
                f.write(f"COUNTRY: {COUNTRIES[code]} (candidate {n})\n")
                f.write(f"IP: {proxy['ip']}\n")
                f.write(f"PORT: {proxy['port']}\n")
                f.write(f"PROTOCOL: {PROTOCOL}\n")
                f.write(f"ANONYMITY: {proxy.get('anonymity', 'N/A')}\n")
                f.write(f"UPTIME: {proxy.get('uptime_percent', 'N/A')}%\n")
                f.write(f"REPO LATENCY: {proxy.get('latency_ms', 'N/A')} ms\n")
                f.write(f"REAL LATENCY: {proxy.get('tcp_latency_ms', 'N/A')} ms\n")
                f.write(f"EXIT IP: {proxy.get('exit_ip', 'N/A')}\n")
                f.write(f"EXIT COUNTRY: {proxy.get('exit_country', 'N/A')}\n")
                f.write(f"ISP: {proxy.get('isp', 'N/A')}\n")
                f.write(f"ASN: {proxy.get('asn', 'N/A')}\n")
                f.write(f"LAST CHECKED: {proxy.get('last_checked', 'N/A')}\n")
                f.write("-" * 45 + "\n\n")

    # Lista simple para proxychains: la cadena verificada, o la primera de cada país
    if working_chain:
        chain = working_chain
    else:
        chain = [(c, p[0]) for c, p in verified_by_country.items() if p]

    with open("proxies.txt", "w", encoding="utf-8") as f:
        for _, proxy in chain:
            f.write(f"socks5 {proxy['ip']} {proxy['port']}\n")

    # Config strict: la cadena probada (solo tiene sentido si se verificó)
    with open("proxychains_strict.conf", "w", encoding="utf-8") as f:
        status = (f"# Chain VERIFIED on {timestamp}, exit IP {chain_exit_ip}\n"
                  if working_chain else
                  "# WARNING: chain NOT verified, may fail\n")
        f.write(status)
        f.write(build_config("strict_chain", chain))

    # Config dynamic: todos los candidatos, salta los muertos
    all_proxies = [(c, p) for c, plist in verified_by_country.items() for p in plist]
    with open("proxychains_dynamic.conf", "w", encoding="utf-8") as f:
        f.write(f"# Dynamic chain with all verified candidates ({timestamp})\n")
        f.write(build_config("dynamic_chain", all_proxies))

    # Metadatos completos
    with open("selected_proxies.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "chain_verified": bool(working_chain),
                "chain_exit_ip": chain_exit_ip,
                "proxies": verified_by_country,
            },
            f, indent=4, ensure_ascii=False,
        )

    print("\n[+] Files generated:")
    for name in ("selected_proxies.txt", "proxies.txt", "proxychains_strict.conf",
                 "proxychains_dynamic.conf", "selected_proxies.json"):
        print(f"    {name}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    if not shutil.which("curl"):
        print("[!] curl is required but was not found in PATH.")
        return

    print("=" * 45)
    print(" SOCKS5 PROXY FINDER v2")
    print(" Minimum anonymity: anonymous")
    print(f" Real-traffic check, {KEEP_PER_COUNTRY} candidates per country")
    print("=" * 45)

    verified_by_country = {}
    for code, name in COUNTRIES.items():
        proxies = find_proxies(code, name)
        if proxies:
            verified_by_country[code] = proxies

    print("\n========== SUMMARY ==========\n")
    for code, name in COUNTRIES.items():
        if code in verified_by_country:
            best = verified_by_country[code][0]
            print(f"[OK] {name}: {len(verified_by_country[code])} verified "
                  f"(best {best['ip']}:{best['port']}, {best['anonymity']})")
        else:
            print(f"[UNAVAILABLE] {name}")

    if not verified_by_country:
        print("\n[!] No working proxies found. Nothing saved.")
        return

    working_chain, chain_exit_ip = None, None

    if TEST_CHAIN:
        if shutil.which("proxychains4"):
            print("\n[+] Testing full chains with proxychains4...")
            working_chain, chain_exit_ip = find_working_chain(verified_by_country)
            if not working_chain:
                print("[!] No full chain worked. Use proxychains_dynamic.conf "
                      "or try fewer hops.")
        else:
            print("\n[!] proxychains4 not found: skipping chain test.")

    save_results(verified_by_country, working_chain, chain_exit_ip)

    if len(verified_by_country) < len(COUNTRIES):
        print("\n[!] Proxies were not found for all requested countries.")
    elif working_chain:
        print("\n[+] A full chain was verified. Use proxychains_strict.conf")
    else:
        print("\n[+] Individual proxies verified; chain not confirmed. "
              "Try proxychains_dynamic.conf")


if __name__ == "__main__":
    main()