"""The single record shape every source is converted into."""

from dataclasses import asdict, dataclass, field


@dataclass
class SourceRecord:
    source: str                 # overture | ontario_moh | osm
    source_id: str              # id within that source
    licence: str                # licence of this record, for attribution
    name: str
    lat: float | None
    lon: float | None
    address: str = ""           # street line as given
    city: str = ""
    postal_code: str = ""       # normalized "A1A 1A1" when known
    phones: list[str] = field(default_factory=list)    # 10-digit strings
    emails: list[str] = field(default_factory=list)    # lower-case
    websites: list[str] = field(default_factory=list)  # as given
    category: str = ""          # source's own category
    raw_type: str = ""          # extra type detail from the source
    fsa_guess: str = ""         # estimated from the nearest record with a postal code, if none given

    @property
    def fsa(self) -> str:
        return self.postal_code[:3] if self.postal_code else self.fsa_guess

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fsa"] = self.fsa
        return d
