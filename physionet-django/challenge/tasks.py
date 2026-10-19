"""
Background tasks for challenge phase transitions.
"""
import logging

from background_task import background

from challenge.models import Challenge
from console.tasks import associated_task

logger = logging.getLogger(__name__)


@associated_task(Challenge, 'challenge_id')
@background()
def transition_challenge_phase(challenge_id, target_phase):
    """Transition a challenge to a new phase and notify participants."""
    from challenge.utility import notify_phase_change

    try:
        challenge = Challenge.objects.get(pk=challenge_id)
    except Challenge.DoesNotExist:
        logger.error('Challenge %s not found', challenge_id)
        return

    old_phase = challenge.phase
    challenge.phase = target_phase
    challenge.save(update_fields=['phase'])

    notify_phase_change(challenge, old_phase, target_phase)
    logger.info('Challenge %s transitioned from %s to %s',
                challenge.slug, old_phase, target_phase)
