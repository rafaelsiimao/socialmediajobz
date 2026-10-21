from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.composer.models import Post
from apps.media_library.models import MediaAsset
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


class MultiSlidePreviewAndOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="slides@example.com", password="testpass123", tos_accepted_at=timezone.now()
        )
        self.org = Organization.objects.create(name="Jobz Org")
        self.workspace = Workspace.objects.create(organization=self.org, name="Jobz Workspace")
        OrgMembership.objects.create(
            user=self.user,
            organization=self.org,
            org_role=OrgMembership.OrgRole.OWNER,
        )
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
        )

        self.ig_account = SocialAccount.objects.create(
            workspace=self.workspace,
            platform="instagram",
            account_platform_id="ig-jobz",
            account_name="jobzcarreira",
            connection_status=SocialAccount.ConnectionStatus.CONNECTED,
        )

        self.client.force_login(self.user)
        self.preview_url = reverse("composer:preview", kwargs={"workspace_id": self.workspace.id})
        self.save_url = reverse("composer:save_post", kwargs={"workspace_id": self.workspace.id})
        self.autosave_url = reverse("composer:autosave", kwargs={"workspace_id": self.workspace.id})

    def _create_asset(self, filename):
        return MediaAsset.objects.create(
            organization=self.org,
            workspace=self.workspace,
            uploaded_by=self.user,
            file=f"media_library/tests/{filename}",
            filename=filename,
            media_type=MediaAsset.MediaType.IMAGE,
            mime_type="image/png",
            file_size=1024,
            source="upload",
        )

    def test_preview_shows_uploaded_image_without_caption(self):
        asset = self._create_asset("image_without_caption.png")
        response = self.client.get(
            self.preview_url,
            {"selected_accounts": str(self.ig_account.id), "media_ids": [str(asset.id)]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["previews"]), 1)
        self.assertEqual(response.context["previews"][0]["caption"], "")
        self.assertContains(response, asset.file.url)
        self.assertNotContains(response, "Nenhuma prévia ainda")

    def test_preview_preserves_exact_order_and_count_for_seven_slides(self):
        assets = [self._create_asset(f"slide_{i}.png") for i in range(1, 8)]
        # Reorder intentionally: 3, 1, 4, 2, 7, 5, 6
        custom_order = [assets[2], assets[0], assets[3], assets[1], assets[6], assets[4], assets[5]]
        media_ids = [str(a.id) for a in custom_order]

        response = self.client.get(
            self.preview_url,
            {
                "title": "Post Jobz",
                "caption": "Carrossel com 7 slides",
                "selected_accounts": str(self.ig_account.id),
                "media_ids": media_ids,
            },
        )
        self.assertEqual(response.status_code, 200)
        items = response.context["media_items"]
        self.assertEqual(len(items), 7)
        expected_filenames = [a.filename for a in custom_order]
        actual_filenames = [item["filename"] for item in items]
        self.assertEqual(actual_filenames, expected_filenames)

    def test_save_post_persists_all_seven_slides_with_correct_positions(self):
        assets = [self._create_asset(f"slide_{i}.png") for i in range(1, 8)]
        media_ids = [str(a.id) for a in assets]

        response = self.client.post(
            self.save_url,
            {
                "caption": "Meu post com 7 slides",
                "selected_accounts": str(self.ig_account.id),
                "media_ids": media_ids,
                "media_submitted": "1",
                "action": "save_draft",
            },
        )
        self.assertIn(response.status_code, [200, 204, 302])

        post = Post.objects.filter(workspace=self.workspace).first()
        self.assertIsNotNone(post)
        attachments = list(post.media_attachments.select_related("media_asset").order_by("position"))
        self.assertEqual(len(attachments), 7)
        for idx, att in enumerate(attachments):
            self.assertEqual(att.position, idx)
            self.assertEqual(str(att.media_asset_id), media_ids[idx])

    def test_reordering_slides_updates_positions_in_database(self):
        assets = [self._create_asset(f"slide_{i}.png") for i in range(1, 8)]
        initial_order = [str(a.id) for a in assets]

        # Initial save
        self.client.post(
            self.save_url,
            {
                "caption": "Post ordenado",
                "selected_accounts": str(self.ig_account.id),
                "media_ids": initial_order,
                "media_submitted": "1",
                "action": "save_draft",
            },
        )
        post = Post.objects.filter(workspace=self.workspace).first()

        # New order (reverse)
        reversed_order = list(reversed(initial_order))
        edit_url = reverse("composer:save_post_edit", kwargs={"workspace_id": self.workspace.id, "post_id": post.id})
        self.client.post(
            edit_url,
            {
                "caption": "Post reordenado",
                "selected_accounts": str(self.ig_account.id),
                "media_ids": reversed_order,
                "media_submitted": "1",
                "action": "save_draft",
            },
        )

        attachments = list(post.media_attachments.select_related("media_asset").order_by("position"))
        self.assertEqual(len(attachments), 7)
        actual_ids = [str(att.media_asset_id) for att in attachments]
        self.assertEqual(actual_ids, reversed_order)
        for idx, att in enumerate(attachments):
            self.assertEqual(att.position, idx)
