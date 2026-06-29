# Suivi de réapprovisionnement — Darty & Leroy Merlin

Surveille des pages produit Darty / Leroy Merlin et envoie une **notification
push sur ton téléphone** (via [ntfy.sh](https://ntfy.sh)) dès qu'un article
repasse en stock.

Tourne gratuitement sur **GitHub Actions** (cron toutes les 30 min). Pensé pour
un usage temporaire de quelques semaines.

---

## Contenu du dépôt

```
suivi_stock_ci.py                  # le script (run unique, appelé par le cron)
requirements.txt                   # dépendances Python
.github/workflows/stock-check.yml  # le workflow planifié
state.json                         # créé automatiquement, NE PAS committer à la main
```

---

## Comment ça marche

1. Le workflow se déclenche toutes les 30 min (cron).
2. Il lance un Chromium headless (Playwright) qui charge chaque page produit —
   un vrai navigateur permet de contourner les protections anti-bot
   (un simple `requests` renvoie un 403 sur ces deux sites).
3. Le script lit le champ `offers.availability` des données structurées
   schema.org (`<script type="application/ld+json">`) pour déterminer le statut.
4. L'état précédent est conservé entre les runs via le **cache GitHub Actions**
   (`state.json`). Une notification n'est envoyée **que sur la transition**
   rupture → en stock (ou si l'article est déjà dispo au tout premier run).

---

## Installation (≈ 5 min, tout depuis le navigateur)

### 1. Recevoir les notifications

- Installe l'app **ntfy** ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / iOS).
- Choisis un **nom de topic unique et secret** (ex. `restock-midea-7h3k9q`).
  Toute personne connaissant ce nom peut s'y abonner : ne le rends pas public.
- Dans l'app, abonne-toi à ce topic.

### 2. Créer le dépôt

- Sur github.com : **New repository** → coche **Public** (minutes Actions
  gratuites et illimitées) → **Create**.

### 3. Ajouter les fichiers

Via l'interface web (**Add file → Create new file**), recrée les fichiers de ce
dossier en respectant les chemins, notamment
`.github/workflows/stock-check.yml`. Tu peux aussi glisser-déposer les fichiers
avec **Add file → Upload files**.

### 4. Configurer le secret ntfy

- **Settings → Secrets and variables → Actions → New repository secret**
- Nom : `NTFY_TOPIC`
- Valeur : le nom de ton topic (ex. `restock-midea-7h3k9q`)

### 5. Activer et tester

- Onglet **Actions** → autorise l'exécution des workflows si demandé.
- Sélectionne **Suivi stock** → **Run workflow** pour forcer un premier run.
- Le premier run enregistre l'état sans notifier (sauf si déjà en stock).
  Les suivants alertent dès qu'un article repasse dispo.

---

## Personnaliser

### Changer / ajouter des produits

Dans `suivi_stock_ci.py`, édite la liste `PRODUCTS` :

```python
PRODUCTS: list[Product] = [
    Product(name="Mon article", url="https://www.darty.com/..."),
]
```

### Ajuster la fréquence

Dans `stock-check.yml`, modifie la ligne `cron` (syntaxe crontab) :

```yaml
- cron: "*/30 * * * *"   # toutes les 30 min
- cron: "*/15 * * * *"   # toutes les 15 min (sur repo public uniquement)
```

### Tester en local avant de pousser

```bash
pip install -r requirements.txt
python -m playwright install chromium
NTFY_TOPIC=ton-topic python suivi_stock_ci.py
```

---

## Quand tu n'en as plus besoin

Désactive le workflow (**Actions → Suivi stock → ... → Disable workflow**) ou
supprime simplement le dépôt. Aucun coût, aucun engagement.

---

## Dépannage

| Symptôme | Piste |
|---|---|
| `statut indéterminé` dans les logs | Le JSON-LD n'a pas été trouvé. Passe `HEADLESS = False` en local pour observer, ou renseigne un `in_stock_selector` (ex. le bouton « Ajouter au panier »). |
| Toujours bloqué (page vide / timeout) | Ajoute `playwright-stealth` (`pip install playwright-stealth`, puis `stealth_sync(page)` après création de la page). |
| Pas de notification | Vérifie que le secret `NTFY_TOPIC` correspond exactement au topic auquel tu es abonné dans l'app. |
| Le run n'a pas notifié au 1er passage | Normal : la 1re exécution enregistre l'état de référence. L'alerte arrive sur le changement suivant. |

---

## Note

Outil destiné à un **usage personnel** et raisonnable. La cadence de 30 min
reste respectueuse des serveurs ; évite de descendre trop bas. Le respect des
conditions d'utilisation des sites concernés relève de ta responsabilité.
