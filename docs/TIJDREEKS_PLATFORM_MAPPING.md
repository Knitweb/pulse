# Tijdreeks-webplatform: multi-tenancy, delen & collecties op de Knitweb-fabric

Onderdeel van het tijdreeks-webplatform-stappenplan; de centrale
implementatiekaart staat in
[`finfield/web` → `docs/TIJDREEKS_WEBPLATFORM_STAPPENPLAN.md`](https://github.com/FinField/web).

Het externe rapport ontwerpt een centraal gehost platform en besteedt
zijn zwaarste hoofdstukken aan wat daar het moeilijkst is: tenants
scheiden in een gedeelde database (`user_id`-filters, RBAC/ABAC),
een expliciet deelsysteem (privé/publiek per dataset), privécollecties
(`UserCollections`/`CollectionItems`) en gelaagde beveiliging
(encryptie, isolatie op infrastructuurniveau, audits). Dit document
legt vast hoe diezelfde behoeften op de Knitweb-fabric landen — waar de
meeste van die mechanismen niet nagebouwd hoeven te worden, omdat het
ontwerp de aanvalsvlakken niet heeft.

## Multi-tenancy → accounts met eigen sleutels

Het rapport waarschuwt: een gedeelde database met tenant-id's is
efficiënt, maar één vergeten `WHERE user_id=` is een datalek. Op de
fabric bestaat dat gedeelde schrijfpad niet:

- Elke deelnemer publiceert onder een **eigen secp256k1-sleutel**; elk
  record is ondertekend en content-geadresseerd
  (`knitweb.core.crypto`, `core.canonical.cid`).
- Eigendom is geen kolom maar een **handtekening**: een record is
  onvervalsbaar aan zijn auteur gebonden, en een `Knit` namespacet zijn
  PLS-web via het hash-kritische `network`-id-veld tegen replay.
- De "auditing" die het rapport als compenserende maatregel eist, is
  hier het normale leesproces: iedereen kan elke handtekening en CID
  onafhankelijk verifiëren.

Personhood-tickets leveren daarbovenop wat RBAC in het rapport moet
leveren: niet "welke rol heeft dit account", maar "is dit één mens" —
één persoon, één stem in elke poll die kwaliteit of correctheid beslecht.

## Privé vs. publiek → publiceren is de grens

Het rapport modelleert een `is_public`-vlag plus API-checks. Op de
fabric is de grens fysiek:

- **Publiek** = ondertekend geweven en gerelayed: zichtbaar, citeerbaar,
  stembaar voor het hele web.
- **Privé** = niet gepubliceerd: een lokale `Braid`/spool op de eigen
  node (zoals de ongetekende drafts van de finagents-spool). Er is geen
  serverkant die per ongeluk tóch kan tonen wat privé had moeten
  blijven.
- **Gevoelige inhoud** (PII, boekhouding) hoort niet versleuteld "op
  het web geparkeerd" maar lokaal in een encrypted vault — het
  LedgerField-patroon (AES-GCM, offline-first, opt-in delen).

Wat het rapport "anoniem delen" noemt, is hier een pseudonieme sleutel:
publiceren onder een vers sleutelpaar deelt de data zonder de identiteit,
terwijl het trackrecord van die sleutel gewoon opbouwt.

## Privécollecties → ondertekende CID-lijsten

De rapport-tabellen `UserCollections`/`CollectionItems` vertalen
één-op-één naar fabric-begrippen:

- een **collectie** is een ondertekend record van de eigenaar met een
  naam en een lijst fact-/knit-CIDs (de `CollectionItems` zijn de
  CID-verwijzingen zelf);
- de collectie is content-geadresseerd: elke revisie heeft zijn eigen
  CID, de geschiedenis is een keten, en delen = de CID (of het record)
  aan een ander geven;
- privé houden = niet publiceren; publiek cureren = wél publiceren, en
  dan kan het web erop voortbouwen en ernaar citeren.

Een expliciet collectie-recordtype (naam + geordende CID-lijst +
handtekening, canoniek gecodeerd) is de enige echte nieuwbouw die dit
rapport-hoofdstuk vraagt; alles eronder (ondertekening, CIDs, relay)
bestaat al. Kandidaat-vervolgstap voor een L5-knitweb of een klein
kern-recordtype — af te wegen tegen de zeven-primitieven-regel.

## Zoeken & ontdekken → indexen zijn lenzen

De zoek-API van het rapport (met permissiefilters in elke query) wordt
hier een **read-only index over gepubliceerde records**: wie indexeert,
ziet per constructie alleen wat publiek is, want privédata komt nooit
langs. De statische zoekindex van finfield/web is daar de eerste vorm
van; rijkere ontdekking (tags, concepten, auteurs-trackrecords) hoort
als lens/digest gebouwd te worden, met citaties, conform het
Lens-contract.

## Beveiliging (rapport §III.C) — wat overblijft

Van de rapport-checklist blijft op de fabric dit over als echt werk:

- **Transportbeveiliging**: TLS op relays en hosting — gewoon doen.
- **Sleutelbeheer**: de zwakste plek verschuift van "de database" naar
  "de sleutel van de deelnemer"; documentatie en tooling voor veilige
  sleutelopslag en -rotatie wegen zwaarder dan welke serverconfig ook.
- **Doorlopende audits**: het rapport-advies "beveiliging is een
  proces" geldt onverkort voor de protocolcode zelf (canonical
  encoding, handtekeningpad, relay-hardening — zie
  `docs/P2P_DHT_ECLIPSE_HARDENING.md`).

Niet overnemen: tenant-specifieke encryptiesleutels per databaserij,
VPC-/namespace-isolatie tussen tenants, rij-niveau-permissiefilters —
dat zijn oplossingen voor een gedeelde serverdatabase die dit ontwerp
niet heeft.
