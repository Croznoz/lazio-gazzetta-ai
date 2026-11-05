from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from google.genai import interactions, types
from youtube_transcript_api import TranscriptsDisabled

import app

V1 = app.Video("aaaaaaaaaaa", 'Lazio: novità "in campo"', "2026-11-03T10:00:00Z")
V2 = app.Video("bbbbbbbbbbb", "Analisi della partita", "2026-11-04T10:00:00Z")
V3 = app.Video("ccccccccccc", "Nuovo allenamento")
ARTICLE = (
    "Lazio, segnali dal campo\n\n"
    + "La squadra cerca continuità attraverso il lavoro tattico. " * 8
)
FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
<title>Dentro la Lazio</title>
<entry><id>yt:video:bbbbbbbbbbb</id><yt:videoId>bbbbbbbbbbb</yt:videoId>
<title>Nuovo video</title><published>2026-11-04T10:00:00Z</published></entry>
<entry><id>yt:video:aaaaaaaaaaa</id><yt:videoId>aaaaaaaaaaa</yt:videoId>
<title>Primo video</title><published>2026-11-03T10:00:00Z</published></entry>
</feed>"""


class ConfigTests(unittest.TestCase):
    def test_defaults_and_no_key_for_preview(self):
        with patch.dict(os.environ, {}, clear=True):
            config = app.Config.from_env()
        self.assertIn(app.DEFAULT_CHANNEL_ID, config.feed_url)
        self.assertEqual(config.api_key, "")

    def test_reject_search_page_as_feed(self):
        with patch.dict(
            os.environ,
            {"YOUTUBE_FEED_URL": "https://www.youtube.com/results?search_query=lazio"},
            clear=True,
        ):
            with self.assertRaises(ValueError):
                app.Config.from_env()

    def test_invalid_configuration(self):
        for env in (
            {"YOUTUBE_CHANNEL_ID": "../../bad"},
            {"MAX_VIDEOS_PER_RUN": "0"},
            {"MAX_VIDEOS_PER_RUN": "abc"},
            {"TRANSCRIPT_LANGUAGES": " , "},
            {"GEMINI_MODEL": " "},
            {"YOUTUBE_PROXY_URL": "invalid"},
            {"YOUTUBE_VIDEO_FALLBACK": "invalid"},
        ):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError):
                    app.Config.from_env()


class FeedTests(unittest.TestCase):
    def test_all_videos_oldest_first_and_no_duplicates(self):
        duplicate_feed = FEED.replace(
            b"</feed>", FEED[FEED.index(b"<entry>") : FEED.index(b"</entry>") + 8] + b"</feed>"
        )
        self.assertEqual(
            [v.video_id for v in app.parse_videos(duplicate_feed)], [V1.video_id, V2.video_id]
        )

    def test_bad_response_rejected(self):
        for content in (
            b"<html>Consent required</html>",
            b"broken XML",
            FEED.replace(b"aaaaaaaaaaa", b"invalid"),
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                app.parse_videos(content)

    def test_valid_empty_feed(self):
        self.assertEqual(
            app.parse_videos(
                b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Empty</title></feed>'
            ),
            [],
        )

    def test_network_failure_does_not_become_empty_feed(self):
        with patch.object(app, "TimeoutSession") as session:
            response = session.return_value.__enter__.return_value.get.return_value
            response.raise_for_status.side_effect = app.requests.HTTPError()
            with self.assertRaises(app.requests.HTTPError):
                app.get_videos("https://www.youtube.com/feeds/videos.xml")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = app.Config(
            "https://example.invalid",
            "test-key",
            output_dir=self.root / "articoli",
            processed_file=self.root / "processed.txt",
            min_generation_interval=0,
        )
        self.feed = patch.object(app, "get_videos", return_value=[V1, V2, V3]).start()
        self.transcript = patch.object(
            app, "get_transcript", return_value="Trascrizione del video."
        ).start()
        self.generate = patch.object(app, "generate_article", return_value=ARTICLE).start()
        self.addCleanup(patch.stopall)

    def test_batch_is_saved_and_rerun_does_not_call_providers(self):
        self.assertEqual(app.run(self.config), 0)
        self.assertEqual(len(list(self.config.output_dir.glob("*.txt"))), 3)
        self.assertEqual(list(self.config.output_dir.glob("*.md")), [])
        self.assertEqual(
            app.load_processed(self.config.processed_file), {V1.video_id, V2.video_id, V3.video_id}
        )
        self.generate.reset_mock()
        self.transcript.reset_mock()
        self.assertEqual(app.run(self.config), 0)
        self.generate.assert_not_called()
        self.transcript.assert_not_called()

    def test_dry_run_needs_no_key_and_writes_nothing(self):
        config = app.Config(
            self.config.feed_url,
            output_dir=self.config.output_dir,
            processed_file=self.config.processed_file,
        )
        self.assertEqual(app.run(config, dry_run=True), 0)
        self.assertEqual(list(self.root.iterdir()), [])
        self.generate.assert_not_called()
        self.transcript.assert_not_called()

    def test_missing_key_is_reported_before_calling_providers(self):
        config = app.Config(
            self.config.feed_url,
            output_dir=self.config.output_dir,
            processed_file=self.config.processed_file,
        )
        with self.assertLogs("lazio", "ERROR") as logs:
            self.assertEqual(app.run(config), 1)
        self.assertIn("GEMINI_API_KEY mancante", " ".join(logs.output))
        self.generate.assert_not_called()
        self.transcript.assert_not_called()

    def test_pending_subtitles_do_not_starve_newer_videos(self):
        self.transcript.side_effect = [None, None, "Trascrizione"]
        config = app.Config(
            self.config.feed_url,
            "key",
            max_videos=1,
            output_dir=self.config.output_dir,
            processed_file=self.config.processed_file,
            video_fallback=False,
        )
        self.assertEqual(app.run(config), 0)
        self.assertEqual(app.load_processed(config.processed_file), {V3.video_id})

    def test_generation_limit_leaves_rest_for_next_run(self):
        config = app.Config(
            self.config.feed_url,
            "key",
            max_videos=1,
            output_dir=self.config.output_dir,
            processed_file=self.config.processed_file,
        )
        self.assertEqual(app.run(config), 0)
        self.assertEqual(self.generate.call_count, 1)
        self.assertEqual(app.load_processed(config.processed_file), {V1.video_id})

    def test_partial_failure_saves_successes_and_retries_failed_video(self):
        self.generate.side_effect = [RuntimeError("private-key-must-not-leak"), ARTICLE, ARTICLE]
        with self.assertLogs("lazio", "INFO") as logs:
            self.assertEqual(app.run(self.config), 1)
        self.assertNotIn("private-key-must-not-leak", " ".join(logs.output))
        self.assertEqual(app.load_processed(self.config.processed_file), {V2.video_id, V3.video_id})
        self.generate.side_effect = None
        self.generate.reset_mock()
        self.assertEqual(app.run(self.config), 0)
        self.generate.assert_called_once()

    def test_blocked_subtitles_use_gemini_video_input(self):
        self.feed.return_value = [V1]
        self.transcript.side_effect = app.RequestBlocked(V1.video_id)
        self.assertEqual(app.run(self.config), 0)
        self.generate.assert_called_once_with(V1, None, self.config)
        path = app.article_path(self.config.output_dir, V1)
        self.assertEqual(path.read_text(encoding="utf-8"), ARTICLE.strip() + "\n")
        self.assertEqual(app.load_processed(self.config.processed_file), {V1.video_id})

    def test_video_fallback_can_be_disabled(self):
        self.feed.return_value = [V1]
        self.transcript.side_effect = app.IpBlocked(V1.video_id)
        config = replace(self.config, video_fallback=False)
        self.assertEqual(app.run(config), 1)
        self.generate.assert_not_called()
        self.assertFalse(config.processed_file.exists())

    def test_network_errors_do_not_trigger_video_fallback(self):
        self.feed.return_value = [V1]
        self.transcript.side_effect = app.requests.Timeout()
        self.assertEqual(app.run(self.config), 1)
        self.generate.assert_not_called()

    def test_quota_exhaustion_stops_calls_and_keeps_previous_success(self):
        self.generate.side_effect = [
            ARTICLE,
            app.errors.ClientError(429, {"error": {"code": 429, "message": "quota"}}),
            ARTICLE,
        ]
        self.assertEqual(app.run(self.config), 1)
        self.assertEqual(self.generate.call_count, 2)
        self.assertEqual(app.load_processed(self.config.processed_file), {V1.video_id})

    def test_server_error_reports_http_status_without_leaking_provider_message(self):
        self.generate.side_effect = [
            app.errors.ServerError(503, {"error": {"code": 503, "message": "private-key"}}),
            ARTICLE,
            ARTICLE,
        ]
        with self.assertLogs("lazio", "INFO") as logs:
            self.assertEqual(app.run(self.config), 1)
        self.assertIn("HTTP 503", " ".join(logs.output))
        self.assertNotIn("private-key", " ".join(logs.output))
        self.assertEqual(app.load_processed(self.config.processed_file), {V2.video_id, V3.video_id})

    def test_recover_existing_file_after_title_change_without_key(self):
        self.feed.return_value = [V1]
        app.atomic_write(self.config.output_dir / f"{V1.video_id}_vecchio-titolo.txt", ARTICLE)
        config = app.Config(
            self.config.feed_url,
            output_dir=self.config.output_dir,
            processed_file=self.config.processed_file,
        )
        self.assertEqual(app.run(config), 0)
        self.generate.assert_not_called()
        self.transcript.assert_not_called()
        self.assertEqual(app.load_processed(config.processed_file), {V1.video_id})

    def test_crash_while_saving_state_is_recoverable_without_second_generation(self):
        self.feed.return_value = [V1]
        with patch.object(app, "mark_processed", side_effect=OSError("disk full")):
            self.assertEqual(app.run(self.config), 1)
        self.assertTrue(app.existing_article(self.config.output_dir, V1.video_id))
        self.assertFalse(self.config.processed_file.exists())
        self.generate.reset_mock()
        self.assertEqual(app.run(self.config), 0)
        self.generate.assert_not_called()

    def test_article_write_failure_does_not_mark_processed(self):
        self.feed.return_value = [V1]
        with patch.object(app, "atomic_write", side_effect=OSError("disk full")):
            self.assertEqual(app.run(self.config), 1)
        self.assertFalse(self.config.processed_file.exists())

    def test_filename_cannot_escape_output_and_file_contains_only_article(self):
        video = app.Video(V1.video_id, '../../Làzio: "novità"\n---')
        path = app.article_path(self.config.output_dir, video)
        self.assertEqual(path.parent, self.config.output_dir)
        self.assertEqual(path.suffix, ".txt")
        rendered = app.render_article(ARTICLE)
        self.assertEqual(rendered, ARTICLE.strip() + "\n")
        self.assertNotIn(video.url, rendered)
        self.assertNotIn("source_", rendered)

    def test_source_reference_is_rejected_before_writing_or_marking_processed(self):
        self.feed.return_value = [V1]
        self.generate.return_value = ARTICLE + "\n\nSecondo Paolo Colantoni la squadra è pronta."
        self.assertEqual(app.run(self.config), 1)
        self.assertFalse(self.config.processed_file.exists())
        self.assertFalse(self.config.output_dir.exists())

    def test_today_filter_ignores_backlog(self):
        self.feed.return_value = [V1, V2]
        self.assertEqual(app.run(self.config, video_date=date(2026, 11, 4)), 0)
        self.generate.assert_called_once_with(V2, "Trascrizione del video.", self.config)

    def test_latest_first_does_not_spend_quota_on_backlog(self):
        self.assertEqual(app.run(replace(self.config, max_videos=1), latest_first=True), 0)
        self.assertEqual(self.generate.call_args.args[0], V3)

    def test_missing_subtitles_also_use_video_fallback(self):
        self.feed.return_value = [V1]
        self.transcript.return_value = None
        self.assertEqual(app.run(self.config), 0)
        self.generate.assert_called_once_with(V1, None, self.config)

    def test_deleted_article_is_recreated_even_if_marked_processed(self):
        self.feed.return_value = [V1]
        self.assertEqual(app.run(self.config), 0)
        path = app.article_path(self.config.output_dir, V1)
        path.unlink()
        self.generate.reset_mock()
        self.assertEqual(app.run(self.config), 0)
        self.generate.assert_called_once()
        self.assertTrue(path.is_file())
        self.assertEqual(len(app.load_index(self.config.output_dir)), 1)

    def test_interval_is_respected_between_generation_starts(self):
        self.feed.return_value = [V1, V2]
        with (
            patch.object(app.time, "monotonic", side_effect=[0, 10, 60, 60]),
            patch.object(app.time, "sleep") as sleep,
        ):
            self.assertEqual(app.run(replace(self.config, min_generation_interval=60)), 0)
        sleep.assert_called_once_with(50)

    def test_github_summary_reports_results(self):
        self.feed.return_value = [V1]
        summary = self.root / "summary.md"
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
            self.assertEqual(app.run(self.config), 0)
        text = summary.read_text()
        self.assertIn("Creati: 1.", text)
        self.assertIn("ancora da elaborare: 0.", text)
        self.assertIn(app.article_path(self.config.output_dir, V1).name, text)


class ArticleIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_sequential_names_use_rome_time_and_survive_title_changes(self):
        stamp = datetime.fromisoformat("2026-11-05T11:30:49+00:00")
        first = app.reserve_article(self.root, V1, created_at=stamp)
        second = app.reserve_article(self.root, V2, created_at=stamp)
        self.assertEqual(first.name, "0001-2026-11-05-12-30-49.txt")
        self.assertEqual(second.name, "0002-2026-11-05-12-30-49.txt")
        renamed = replace(V1, title="Titolo modificato")
        self.assertEqual(app.article_path(self.root, renamed), first)

    def test_pending_reservation_can_be_reused_without_skipping_number(self):
        first = app.reserve_article(self.root, V1)
        self.assertFalse(app.existing_article(self.root, V1.video_id))
        self.assertEqual(app.reserve_article(self.root, V1), first)
        app.atomic_write(first, ARTICLE)
        self.assertTrue(app.existing_article(self.root, V1.video_id))

    def test_migration_preserves_text_and_is_idempotent(self):
        old = self.root / f"{V1.video_id}_titolo.txt"
        app.atomic_write(old, ARTICLE)
        with patch.object(app.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            self.assertEqual(app.rename_articles(self.root), 1)
            self.assertEqual(app.rename_articles(self.root), 0)
        path = app.article_path(self.root, V1)
        self.assertFalse(old.exists())
        self.assertEqual(path.read_text(), ARTICLE)
        self.assertTrue(app.existing_article(self.root, V1.video_id))

    def test_index_rejects_path_traversal_and_duplicate_numbers(self):
        for index in (
            {V1.video_id: {"file": "../../outside.txt"}},
            {
                V1.video_id: {"file": "0001-2026-11-05-12-00-00.txt"},
                V2.video_id: {"file": "0001-2026-11-05-13-00-00.txt"},
            },
        ):
            app.save_index(self.root, index)
            with self.assertRaises(ValueError):
                app.load_index(self.root)


class DateSelectionTests(unittest.TestCase):
    def test_date_is_italian_calendar_day_across_utc_midnight(self):
        for stamp in ("2026-11-04T23:30:00Z", "2026-07-04T22:30:00Z"):
            video = replace(V1, published_at=stamp)
            day = date(2026, 11, 5) if "11-" in stamp else date(2026, 7, 5)
            self.assertEqual(app.select_videos([video], day), [video])

    def test_missing_or_naive_dates_are_rejected_when_filtering(self):
        for stamp in ("", "2026-11-05T12:00:00"):
            with self.assertRaises(ValueError):
                app.select_videos([replace(V1, published_at=stamp)], date(2026, 11, 5))


class ArticleTextTests(unittest.TestCase):
    def test_source_names_are_removed_from_filename(self):
        video = app.Video(V1.video_id, "Paolo Colantoni - Dentro la Lazio: partita e analisi")
        name = app.article_path(Path("articoli"), video).name
        self.assertNotIn("paolo", name)
        self.assertNotIn("colantoni", name)
        self.assertNotIn("dentro-la-lazio", name)

    def test_markdown_formatting_is_normalized_to_plain_text(self):
        article = (
            "```text\n# Lazio, segnali dal campo\n\n**Squadra compatta**\n\n*"
            + "La squadra cerca continuità. " * 8
            + "*\n```"
        )
        text = app.prepare_article(article)
        self.assertTrue(text.startswith("Lazio, segnali dal campo\n\n"))
        for marker in ("#", "*", "```"):
            self.assertNotIn(marker, text)

    def test_forbidden_source_references_are_rejected(self):
        for reference in (
            "Paolo Colantoni",
            "COLANTONI",
            "Dentro la Lazio",
            "Dentro\nla Lazio",
            "YouTube",
            "https://example.com",
            "nel video",
            "dal video",
            "la trascrizione",
            "il canale",
            "youtu.be/example",
        ):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                app.prepare_article(ARTICLE + "\n\n" + reference)

    def test_metadata_and_unstructured_outputs_are_rejected(self):
        for text in ("---\nsource_url: example\n---\n\n" + ARTICLE, "Titolo breve", "x" * 200):
            with self.subTest(text=text), self.assertRaises(ValueError):
                app.prepare_article(text)


class ProviderTests(unittest.TestCase):
    def test_video_fallback_uses_interactions_with_actual_youtube_input(self):
        config = app.Config("https://example.invalid", "test-key")
        with patch.object(app.genai, "Client") as client:
            api = client.return_value.__enter__.return_value
            api.interactions.create.return_value = interactions.Interaction(
                status="completed",
                steps=[{"type": "model_output", "content": [{"type": "text", "text": ARTICLE}]}],
            )
            self.assertEqual(app.generate_article(V1, None, config), ARTICLE.strip())
            request = api.interactions.create.call_args.kwargs
            self.assertEqual(request["input"][1], {"type": "video", "uri": V1.url})
            self.assertIn("FONTE_NON_DISPONIBILE", request["input"][0]["text"])
            self.assertEqual(request["system_instruction"], app.SYSTEM_PROMPT)
            self.assertEqual(request["model"], app.DEFAULT_MODEL)
            self.assertFalse(request["store"])
            self.assertEqual(request["generation_config"]["thinking_level"], "low")
            self.assertEqual(client.call_args.kwargs["http_options"].retry_options.attempts, 1)
            api.models.generate_content.assert_not_called()

    def test_video_response_must_be_completed_and_contain_an_article(self):
        with patch.object(app.genai, "Client") as client:
            create = client.return_value.__enter__.return_value.interactions.create
            for status, text in (
                ("in_progress", ARTICLE),
                ("failed", ""),
                ("completed", "FONTE_NON_DISPONIBILE"),
                ("completed", ""),
            ):
                with self.subTest(status=status, text=text):
                    create.return_value = interactions.Interaction(
                        status=status,
                        steps=[
                            {"type": "model_output", "content": [{"type": "text", "text": text}]}
                        ],
                    )
                    with self.assertRaises(ValueError):
                        app.generate_article(V1, None, app.Config("", "key"))

    def test_interactions_http_errors_preserve_quota_and_server_status(self):
        class InteractionError(Exception):
            def __init__(self, status):
                super().__init__("private-provider-message")
                self.status_code = status

        with patch.object(app.genai, "Client") as client:
            create = client.return_value.__enter__.return_value.interactions.create
            for status, expected in ((429, app.errors.ClientError), (503, app.errors.ServerError)):
                with self.subTest(status=status):
                    create.side_effect = InteractionError(status)
                    with self.assertRaises(expected) as caught:
                        app.generate_article(V1, None, app.Config("", "key"))
                    self.assertEqual(caught.exception.code, status)
                    self.assertNotIn("private-provider-message", str(caught.exception))

    def test_current_transcript_api_and_unavailable_subtitles(self):
        config = app.Config("https://example.invalid")
        with patch.object(app, "YouTubeTranscriptApi") as api:
            api.return_value.fetch.return_value = [
                SimpleNamespace(text="Lazio &amp; calcio\n oggi")
            ]
            self.assertEqual(app.get_transcript(V1.video_id, config), "Lazio & calcio oggi")
            api.return_value.fetch.assert_called_once_with(V1.video_id, languages=("it",))
            api.return_value.fetch.side_effect = TranscriptsDisabled(V1.video_id)
            self.assertIsNone(app.get_transcript(V1.video_id, config))

    def test_gemini_response_must_be_complete_and_valid(self):
        config = app.Config("https://example.invalid", "test-key")
        with patch.object(app.genai, "Client") as client:
            model = client.return_value.__enter__.return_value.models.generate_content
            model.return_value = types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        finish_reason=types.FinishReason.STOP,
                        content=types.Content(parts=[types.Part(text=ARTICLE)]),
                    )
                ]
            )
            self.assertEqual(app.generate_article(V1, "Trascrizione", config), ARTICLE.strip())
            self.assertEqual(model.call_args.kwargs["model"], app.DEFAULT_MODEL)
            for response in (
                types.GenerateContentResponse(),
                types.GenerateContentResponse(
                    candidates=[types.Candidate(finish_reason=types.FinishReason.MAX_TOKENS)]
                ),
                types.GenerateContentResponse(
                    candidates=[
                        types.Candidate(
                            finish_reason=types.FinishReason.STOP,
                            content=types.Content(parts=[types.Part(text="")]),
                        )
                    ]
                ),
            ):
                with self.subTest(response=response):
                    model.return_value = response
                    with self.assertRaises(ValueError):
                        app.generate_article(V1, "Trascrizione", config)

    def test_long_transcript_is_not_silently_truncated(self):
        with patch.object(app.genai, "Client") as client:
            with self.assertRaises(ValueError):
                app.generate_article(V1, "x" * 250_001, app.Config("", "key"))
            client.assert_not_called()


class AtomicStateTests(unittest.TestCase):
    def test_failed_replace_keeps_previous_state_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "processed.txt"
            app.atomic_write(path, f"{V1.video_id}\n")
            processed = {V1.video_id}
            with patch.object(Path, "replace", side_effect=OSError("failure")):
                with self.assertRaises(OSError):
                    app.mark_processed(path, processed, V2.video_id)
            self.assertEqual(app.load_processed(path), {V1.video_id})
            self.assertEqual(processed, {V1.video_id})
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
