"""Modèles de configuration des serveurs et du routeur.

La configuration d'un conteneur est stockée dans un label Docker
(`mc-panel.spec`) : le panel n'a donc aucune base de données à maintenir.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
SIZE_RE = re.compile(r"^\d+[KkMmGg]?$")
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")

RestartPolicy = Literal["no", "unless-stopped", "always", "on-failure"]


def _check_env(env: dict[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in env.items():
        if not ENV_RE.match(key):
            raise ValueError(f"nom de variable invalide : {key!r}")
        clean[key] = str(value)
    return clean


def _check_tag(tag: str) -> str:
    if not TAG_RE.match(tag):
        raise ValueError("tag d'image invalide")
    return tag


class ServerSpec(BaseModel):
    name: str
    image_tag: str = "latest"
    memory: str = "2G"                  # tas JVM -> variable MEMORY
    mem_limit: str | None = None        # limite dure du conteneur (ex. 3G)
    cpu_limit: float | None = Field(default=None, gt=0, le=256)
    hosts: str = ""                     # hostnames mc-router, séparés par des virgules
    host_port: int | None = Field(default=None, ge=1, le=65535)
    router_default: bool = False        # serveur par défaut de mc-router
    data_path: str | None = None        # dossier hôte (sinon volume nommé)
    restart: RestartPolicy = "unless-stopped"
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("nom invalide (a-z, 0-9, _ et -, 31 caractères max)")
        return v

    @field_validator("image_tag")
    @classmethod
    def _tag(cls, v: str) -> str:
        return _check_tag(v)

    @field_validator("memory", "mem_limit")
    @classmethod
    def _size(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not SIZE_RE.match(v):
            raise ValueError("taille invalide (ex. 2G, 1536M)")
        return v

    @field_validator("hosts")
    @classmethod
    def _hosts(cls, v: str) -> str:
        parts = [p.strip() for p in v.split(",") if p.strip()]
        for p in parts:
            if not HOST_RE.match(p):
                raise ValueError(f"hostname invalide : {p!r}")
        return ",".join(parts)

    @field_validator("data_path")
    @classmethod
    def _path(cls, v: str | None) -> str | None:
        if not v:
            return None
        if not v.startswith("/") or ".." in v.split("/"):
            raise ValueError("chemin absolu requis, sans '..'")
        return v

    @field_validator("env")
    @classmethod
    def _env(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_env(v)


class RouterSpec(BaseModel):
    image_tag: str = "latest"
    host_port: int = Field(default=25565, ge=1, le=65535)
    mappings: str = ""                  # lignes « hostname=backend:port » supplémentaires
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("image_tag")
    @classmethod
    def _tag(cls, v: str) -> str:
        return _check_tag(v)

    @field_validator("env")
    @classmethod
    def _env(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_env(v)


class CommandBody(BaseModel):
    command: str = Field(min_length=1, max_length=500)
