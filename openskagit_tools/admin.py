from django.contrib import admin

from .models import McpAccessRequest, McpOAuthAuthorizationCode, McpOAuthClient, McpOAuthGrant


@admin.register(McpAccessRequest)
class McpAccessRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "organization", "agent_client", "expected_volume", "status", "created_at")
    list_filter = ("status", "expected_volume", "created_at")
    search_fields = ("name", "email", "organization", "intended_use")
    readonly_fields = ("ip_address", "user_agent", "created_at")


@admin.register(McpOAuthClient)
class McpOAuthClientAdmin(admin.ModelAdmin):
    list_display = ("name", "client_id", "access_request", "active", "expires_at", "last_used_at", "created_at")
    list_filter = ("active", "created_at")
    search_fields = ("name", "client_id", "access_request__email")
    readonly_fields = ("client_id", "encrypted_client_secret", "created_at", "last_used_at")

    def has_add_permission(self, request):
        return False


@admin.register(McpOAuthAuthorizationCode)
class McpOAuthAuthorizationCodeAdmin(admin.ModelAdmin):
    list_display = ("client", "expires_at", "used_at", "created_at")
    readonly_fields = [field.name for field in McpOAuthAuthorizationCode._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(McpOAuthGrant)
class McpOAuthGrantAdmin(admin.ModelAdmin):
    list_display = ("client", "active", "access_expires_at", "refresh_expires_at", "last_used_at", "created_at")
    list_filter = ("active", "created_at")
    readonly_fields = [field.name for field in McpOAuthGrant._meta.fields]

    def has_add_permission(self, request):
        return False
