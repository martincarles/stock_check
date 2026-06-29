"""Suivi de réapprovisionnement — version run unique pour GitHub Actions.

Contrairement à la version "boucle", ce script fait UNE seule passe puis
s'arrête : c'est le cron du workflow qui le relance toutes les 30 min.
L'état (dernier statut connu de chaque produit) est lu/écrit dans state.json,
fichier persisté entre les runs via le cache GitHub Actions.

Notifie quand un produit devient disponible (transition rupture -> stock,
ou première observation déjà en stock).

Variables d'environnement attendues :
    NTFY_TOPIC   nom du topic ntfy (défini en GitHub Secret)

Usage local :
    NTFY_TOPIC=mon-topic python suivi_stock_ci.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Browser, BrowserContext, sync_playwright

# --- Configuration -----------------------------------------------------------

NTFY_TOPIC: str = os.environ.get("NTFY_TOPIC", "")
STATE_FILE: Path = Path("state.json")
HEADLESS: bool = True

USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class Product:
    name: str
    url: str
    in_stock_selector: Optional[str] = None  # fallback CSS si pas de JSON-LD


PRODUCTS: list[Product] = [
    Product(
        name="Climatiseur Midea PortaSplit (Leroy Merlin)",
        url="https://www.leroymerlin.fr/produits/climatiseur-split-mobile-reversible-portasplit-midea-par-optimea-93857579.html",
    ),
    Product(
        name="Climatiseur Midea MMCS-12HRN8 (Darty)",
        url="https://www.darty.com/nav/achat/gros_electromenager/chauffage_climatisation/climatiseur/midea_mmcs-12hrn8-qrd0.html",
    ),
]


# --- Persistance d'état ------------------------------------------------------

def load_state() -> dict[str, bool]:
    """Charge {url: en_stock} depuis state.json (vide si absent)."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict[str, bool]) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")


# --- Récupération via navigateur ---------------------------------------------

def make_context(browser: Browser) -> BrowserContext:
    return browser.new_context(
        user_agent=USER_AGENT,
        locale="fr-FR",
        timezone_id="Europe/Paris",
        viewport={"width": 1366, "height": 768},
        extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
    )


def fetch_html(context: BrowserContext, url: str) -> Optional[str]:
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(3_000)
        return page.content()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] échec de chargement {url} : {exc}")
        return None
    finally:
        page.close()


# --- Détection du stock ------------------------------------------------------

def _iter_jsonld(html: str) -> Iterator[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        raw: str = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            for node in data:
                if isinstance(node, dict):
                    yield node
        elif isinstance(data, dict):
            yield data


def availability_from_jsonld(html: str) -> Optional[bool]:
    nodes = list(_iter_jsonld(html))
    if not nodes:
        print("[debug] aucun bloc JSON-LD trouvé dans la page")
    for node in nodes:
        print(f"[debug] JSON-LD @type={node.get('@type')} keys={list(node.keys())}")
        offers = node.get("offers")
        if not offers:
            continue
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        availability: str = str(offers.get("availability", "")).lower()
        print(f"[debug] offers.availability = {availability!r}")
        if "instock" in availability or "limitedavailability" in availability:
            return True
        if "outofstock" in availability or "soldout" in availability:
            return False
    return None


def detect_availability(html: str, product: Product) -> Optional[bool]:
    result = availability_from_jsonld(html)
    if result is None and product.in_stock_selector:
        soup = BeautifulSoup(html, "html.parser")
        result = soup.select_one(product.in_stock_selector) is not None
    return result


# --- Notification ------------------------------------------------------------

def notify(title: str, message: str, url: str) -> None:
    if not NTFY_TOPIC:
        print("[warn] NTFY_TOPIC non défini : notification ignorée")
        return
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Click": url,
                "Tags": "package",
                "Priority": "high",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        print(f"[warn] échec notification : {exc}")


# --- Passe unique ------------------------------------------------------------

def run_once() -> int:
    """Vérifie tous les produits une fois. Retourne 0 si OK."""
    state = load_state()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = make_context(browser)
        try:
            for product in PRODUCTS:
                html = fetch_html(context, product.url)
                if html is None:
                    continue
                available = detect_availability(html, product)
                if available is None:
                    print(f"[info] {product.name} : statut indéterminé")
                    continue

                previous = state.get(product.url)  # True / False / None
                print(f"[info] {product.name} : "
                      f"{'EN STOCK' if available else 'rupture'} "
                      f"(précédent : {previous})")

                # Notifie si disponible ET qu'on ne le savait pas déjà en stock
                if available and previous is not True:
                    notify(
                        title=f"De nouveau en stock : {product.name}",
                        message="L'article est de nouveau disponible !",
                        url=product.url,
                    )
                state[product.url] = available
        finally:
            context.close()
            browser.close()

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(run_once())
