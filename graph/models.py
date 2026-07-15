"""Managed persistence for internal parcel relationship graph inputs.

This module does not expose owner identities, mailing addresses, or entity
membership through public views or APIs.
"""
from __future__ import annotations
from django.db import models

class GraphEntity(models.Model):
    entity_id = models.CharField(max_length=64, primary_key=True)
    canonical_name = models.TextField()
    kind = models.CharField(max_length=16, default="unknown")
    raw_name_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = "graph_entities"
        indexes = [models.Index(fields=["kind"], name="graph_entity_kind_idx")]

class GraphEntityParcel(models.Model):
    entity_id = models.CharField(max_length=64)
    parcel_number = models.TextField()
    source = models.CharField(max_length=32, default="assessor")
    class Meta:
        db_table = "graph_entity_parcels"
        constraints = [models.UniqueConstraint(fields=["entity_id", "parcel_number", "source"], name="graph_entity_parcel_unique")]
        indexes = [models.Index(fields=["parcel_number"], name="graph_entity_parcel_pid_idx")]

class GraphOwnershipGroup(models.Model):
    group_id = models.CharField(max_length=64, primary_key=True)
    member_entity_ids = models.JSONField(default=list)
    link_reason = models.CharField(max_length=40)
    mailing_key = models.CharField(max_length=64, blank=True)
    class Meta:
        db_table = "graph_ownership_groups"
        indexes = [models.Index(fields=["link_reason"], name="graph_group_reason_idx")]

class GraphParcelAdjacency(models.Model):
    pid_a = models.TextField()
    pid_b = models.TextField()
    shared_boundary_ft = models.FloatField()
    class Meta:
        db_table = "graph_parcel_adjacency"
        constraints = [models.UniqueConstraint(fields=["pid_a", "pid_b"], name="graph_adjacency_pair_unique")]
        indexes = [models.Index(fields=["pid_a"], name="graph_adjacency_a_idx"), models.Index(fields=["pid_b"], name="graph_adjacency_b_idx")]

class GraphBuildState(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    source_hash = models.CharField(max_length=128, blank=True)
    last_success_at = models.DateTimeField(blank=True, null=True)
    summary = models.JSONField(default=dict)
    class Meta:
        db_table = "graph_build_state"