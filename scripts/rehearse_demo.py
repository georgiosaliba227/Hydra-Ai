#!/usr/bin/env python3
"""Rehearse the synthetic backend demo entirely in process, without networking.

Run with the existing development environment: python scripts/rehearse_demo.py.
This is software verification, not camera accuracy or scientific validation.
"""
import base64
from contextlib import ExitStack, closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import sys
import tempfile
from unittest.mock import patch
from uuid import UUID


class RehearsalFailure(Exception):
    """Contains only a fixed check name, never request or credential data."""


def require(condition: bool, check: str) -> None:
    if not condition:
        raise RehearsalFailure(check)


class SyntheticClock(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 10, 27, 12, tzinfo=timezone.utc)
        return value.replace(tzinfo=None) if tz is None else value.astimezone(tz)


def rehearse() -> dict:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    blocked_attempts = []

    def forbidden(*args, **kwargs):
        blocked_attempts.append(True)
        raise RehearsalFailure('external_transport_or_financial_ledger_attempted')

    # No private dotenv, key, path, account or live configuration is consulted.
    with ExitStack() as guards:
        guards.enter_context(patch.dict(os.environ, {
            'HYDRA_AI_MODE': 'mock', 'META_BILLABLE_REQUESTS_ENABLED': 'false',
        }, clear=True))
        for name in ('create_connection', 'getaddrinfo'):
            guards.enter_context(patch.object(socket, name, forbidden))
        for name in ('connect', 'connect_ex', 'sendto', 'sendmsg'):
            if hasattr(socket.socket, name):
                guards.enter_context(patch.object(socket.socket, name, forbidden))

        from fastapi.testclient import TestClient
        from backend.app import create_app
        from backend.meta_accounts import AccountLedger
        from backend.meta_gateway import GitHubNotifier
        from backend.meta_provider import OfficialMetaTransport

        for target in (OfficialMetaTransport, GitHubNotifier):
            guards.enter_context(patch.object(target, '__init__', forbidden))
        guards.enter_context(patch.object(OfficialMetaTransport, 'generate', forbidden))
        guards.enter_context(patch.object(GitHubNotifier, 'deliver', forbidden))
        guards.enter_context(patch.object(AccountLedger, 'transaction', forbidden))
        guards.enter_context(patch('backend.schemas.datetime', SyntheticClock))
        guards.enter_context(patch('backend.personal_forecasts.datetime', SyntheticClock))

        token = secrets.token_urlsafe(40)
        auth = {'Authorization': 'Bearer ' + token}
        checks = []
        # Minimal JPEG marker fixture accepted only by the non-decoding mock.
        jpeg = b'\xff\xd8\xff\xc0\x00\x0b\x08\x00\x10\x00\x10\x01\x01\x11\x00\xff\xd9'
        image = base64.b64encode(jpeg).decode()
        analysis = {'image_base64': image, 'photo_consent': True, 'mode': 'mock'}
        manual = {'category': 'water', 'consumed_ml': 250, 'consumed_at': '2026-10-27T10:00:00Z',
                  'timezone': 'UTC', 'source': 'manual'}
        manual_headers = auth | {'Idempotency-Key': str(UUID(int=1))}
        summary_query = {'date': '2026-10-27', 'timezone': 'UTC'}

        def records(client):
            response = client.get('/v1/beverages', headers=auth)
            require(response.status_code == 200, 'read_confirmed_logs')
            return response.json()['items']

        with tempfile.TemporaryDirectory(prefix='hydra-offline-demo-') as directory:
            database = Path(directory) / 'synthetic-beverages.sqlite3'
            with TestClient(create_app(database, token)) as client:
                health = client.get('/health').json()
                require(health['ai_mode'] == 'mock' and health['billable_requests_enabled'] is False,
                        'mock_and_billing_disabled')
                require(client.get('/v1/beverages').status_code == 401, 'authentication_required')
                checks.append('mock_mode_and_authentication')
                response = client.post('/v1/beverages', json=manual, headers=manual_headers)
                require(response.status_code == 201, 'manual_250_ml_created')
                manual_record = response.json()
                replay = client.post('/v1/beverages', json=manual, headers=manual_headers)
                require(replay.status_code == 200 and replay.json() == manual_record and len(records(client)) == 1,
                        'manual_idempotent_replay')
                checks.append('manual_log_and_idempotent_replay')

                known = client.post('/v1/recognitions', json=analysis | {'mock_scenario': 'branded'}, headers=auth)
                require(known.status_code == 200 and known.headers['cache-control'] == 'no-store', 'known_mock_recognition')
                known_result = known.json()
                require(known_result['mode'] == 'mock' and known_result['requires_confirmation'] is True,
                        'explicit_confirmation_required')
                candidate = known_result['candidates'][0]
                require(candidate['nutrition']['provenance'] and candidate['nutrition']['water_ml'] is None,
                        'nutrition_provenance_and_unknown_water')
                unknown = client.post('/v1/recognitions', json=analysis | {'mock_scenario': 'missing_nutrition'}, headers=auth)
                require(unknown.status_code == 200 and unknown.json()['candidates'][0]['nutrition'] is None,
                        'unknown_nutrition_preserved')
                ambiguous = client.post('/v1/recognitions', json=analysis | {'mock_scenario': 'ambiguous'}, headers=auth)
                require(ambiguous.status_code == 200 and ambiguous.json()['candidates'] == [], 'ambiguous_has_no_candidate')
                refused = client.post('/v1/recognitions', json=analysis | {'photo_consent': False}, headers=auth)
                failed = client.post('/v1/recognitions', json=analysis | {'mock_scenario': 'failure'}, headers=auth)
                require(refused.status_code == 422 and failed.status_code == 503 and len(records(client)) == 1,
                        'no_consent_and_provider_failure_do_not_log')
                checks.append('known_unknown_ambiguous_and_refused_mock_photo')

                confirmed = manual | {'category': candidate['identity'], 'consumed_ml': 150,
                    'container_ml': candidate['container_ml'], 'product_id': candidate['product_id'],
                    'source': 'confirmed_recognition'}
                response = client.post('/v1/beverages', json=confirmed,
                                       headers=auth | {'Idempotency-Key': str(UUID(int=2))})
                require(response.status_code == 201 and len(records(client)) == 2, 'confirmed_150_ml_created')
                checks.append('separate_explicit_mock_confirmation')
                historical = manual | {'consumed_ml': 500, 'consumed_at': '2026-10-26T10:00:00Z'}
                require(client.post('/v1/beverages', json=historical,
                    headers=auth | {'Idempotency-Key': str(UUID(int=3))}).status_code == 201, 'historical_log_created')

            # Recreate the application against the same disposable file.
            with TestClient(create_app(database, token)) as client:
                require(len(records(client)) == 3, 'restart_preserves_three_confirmed_logs')
                replay = client.post('/v1/beverages', json=manual, headers=manual_headers)
                require(replay.status_code == 200 and replay.json() == manual_record, 'restart_preserves_idempotency')
                response = client.get('/v1/summary', params=summary_query, headers=auth)
                require(response.status_code == 200, 'summary_available_after_restart')
                summary = response.json()
                require(summary['beverage_total_ml'] == 400 and summary['estimated_water_ml'] is None,
                        'summary_preserves_volume_and_unknown_water')
                checks.append('persistent_restart_summary_and_replay')

                conditions = {'activity': 'running', 'intensity': 'moderate', 'temperature_c': 20.0, 'humidity_percent': 60.0}
                forecast_input = summary_query | {'history_days': 7, 'calibration_processing_consent': True,
                    'exercise': {'event_id': str(UUID(int=9)), 'starts_at': '2026-10-27T14:00:00Z',
                        'duration_minutes': 30.0, 'conditions': conditions, 'comparable_conditions_confirmed': True},
                    'samples': [{'event_id': str(UUID(int=8)), 'observed_at': '2026-10-26T12:00:00Z',
                        'conditions': conditions,
                        'measurement': {'pre_mass_kg': 70.0, 'post_mass_kg': 69.0, 'consumed_ml': 400.0,
                            'urine_ml': 0.0, 'duration_minutes': 60.0, 'protocol_confirmed': True,
                            'provenance': ['synthetic-weighing']},
                        'errors': {'pre_mass_kg': .05, 'post_mass_kg': .05, 'consumed_ml': 10.0,
                            'urine_ml': 0.0, 'duration_minutes': 0.0, 'provenance': ['synthetic-instrument-bounds']}}]}
                response = client.post('/v1/forecasts', json=forecast_input, headers=auth)
                require(response.status_code == 200 and response.headers['cache-control'] == 'no-store', 'forecast_available')
                forecast = response.json()
                history, loss = forecast['historical_logged_intake'], forecast['exercise_loss']
                require(history['window_days'] == 7 and history['logged_days'] == 1 and history['days_without_logs'] == 6
                        and history['beverage_lower_ml'] == history['beverage_upper_ml'] == 500, 'seven_day_descriptive_history')
                require(loss['status'] == 'estimated' and (loss['lower_ml'], loss['upper_ml']) == (645, 755)
                        and 'not_a_drinking_target' in loss['assumptions'], 'conditional_exercise_loss_645_to_755')
                require(forecast['daily_requirement']['status'] == 'insufficient_data'
                        and forecast['prediction_validated'] is False, 'no_unapproved_daily_requirement')
                checks.append('descriptive_history_and_conditional_exercise_loss')

                comparison = '/v2/hydration-context-comparison'
                mock = client.post(comparison, json={'mode': 'mock', 'scenario': 'complete'}, headers=auth)
                require(mock.status_code == 200 and mock.json()['provenance']['candidate_model'] == 'muse-wonder-1.0'
                        and mock.json()['provenance']['mode'] == 'mock', 'wonder_only_mock_comparison')
                spark = {'mode': 'mock', 'scenario': 'complete', 'candidate_model': 'muse-spark-1.3'}
                require(client.post(comparison, json=spark, headers=auth).status_code == 422, 'spark_hydration_candidate_refused')
                # No results directory is configured here, so replay must find nothing and never dispatch.
                recorded = client.post(comparison, json={'mode': 'recorded', 'scenario': 'complete'}, headers=auth)
                require(recorded.status_code == 404, 'unrecorded_wonder_replay_unavailable')
                checks.append('wonder_mock_and_recorded_replay_without_dispatch')

                answer = client.post('/v1/assistant', json={'question_id': 'creatine_water'}, headers=auth)
                require(answer.status_code == 200 and answer.json()['topics'] == ['creatine']
                        and answer.json()['provenance']['mode'] == 'local_rules', 'assistant_reviewed_answer')
                urgent = client.post('/v1/assistant', json={'question': 'I fainted after my run'}, headers=auth).json()
                require(urgent['escalation'] is True and urgent['topics'][0] == 'urgent', 'assistant_urgent_escalation')
                recorded_answer = {'question_id': 'creatine_water', 'source': 'recorded_wonder'}
                require(client.post('/v1/assistant', json=recorded_answer, headers=auth).status_code == 404,
                        'unrecorded_wonder_answer_unavailable')
                checks.append('assistant_reviewed_answers_and_urgent_escalation')

            with closing(sqlite3.connect(database)) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                require(tables == {'beverages', 'settings'}, 'no_financial_or_calibration_tables')
                for (stored,) in connection.execute('SELECT record_json FROM beverages'):
                    require(image not in stored and 'pre_mass_kg' not in stored and 'synthetic-weighing' not in stored,
                            'no_photo_or_raw_calibration_persistence')
            require(not blocked_attempts, 'no_network_transport_or_financial_ledger_attempts')
            checks.append('no_network_or_financial_ledger_or_raw_input_persistence')

        return {'status': 'passed', 'scope': 'synthetic_backend_only', 'synthetic_clock_utc': '2026-10-27T12:00:00Z',
                'checks': checks, 'confirmed_records_after_restart': 3, 'today_beverage_ml': 400,
                'today_estimated_water_ml': None, 'history': {'window_days': 7, 'logged_days': 1, 'days_without_logs': 6},
                'exercise_loss_ml': [645, 755], 'exercise_range_is_drinking_target': False,
                'daily_requirement': 'insufficient_data', 'prediction_validated': False,
                'billable_requests_enabled': False, 'financial_ledger_used': False, 'network_attempts': 0}


if __name__ == '__main__':
    try:
        print(json.dumps(rehearse(), separators=(',', ':'), allow_nan=False))
    except RehearsalFailure as error:
        print(json.dumps({'status': 'failed', 'check': str(error)}, separators=(',', ':')))
        raise SystemExit(1) from None
    except Exception:
        print(json.dumps({'status': 'failed', 'check': 'unexpected_rehearsal_failure'}, separators=(',', ':')))
        raise SystemExit(1) from None
