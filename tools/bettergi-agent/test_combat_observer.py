"""Synthetic refusal and timing cases; these fixtures do not establish real enemy recognition accuracy."""
import unittest
import numpy as np
from combat_observer import CombatObserver,inspect_pixels


def pixels(bars=((90,70,12,2),),health=True):
    """Create inert RGB samples with known color regions, without launching the game."""
    image=np.zeros((192,192,3),dtype=np.uint8)
    for x,y,w,h in bars:image[y:y+h,x:x+w]=[255,90,90]
    if health:image[180:182,80:110]=[140,200,70]
    return image.tobytes()


def frame(index,stamp,epoch='capture-one'):
    """Supply only the source identity consumed by this read-only observer."""
    return dict(frameId=index,sourceFrame=dict(timestamp100ns=stamp,captureEpoch=epoch))


class CombatObserverTests(unittest.TestCase):
    def test_candidate_never_claims_input_authority_or_a_kill(self):
        result=inspect_pixels(pixels())
        self.assertEqual(result['enemyBarCandidates'][0]['width'],12)
        self.assertEqual(result['playerHealthColor'],'green-visible')
        self.assertFalse(result['authorizesInput'] or result['enemyIdentityVerified'] or result['killVerified'])

    def test_hud_red_icons_vertical_shapes_and_missing_health_do_not_confirm(self):
        for image in (pixels(((10,10,12,2),)),pixels(((90,70,2,12),)),pixels(health=False)):
            observer=CombatObserver()
            observer.observe(frame(1,1000000),image)
            self.assertFalse(observer.observe(frame(2,2000000),image)['temporalCandidateConfirmed'])

    def test_repeated_sources_and_close_capture_clocks_cannot_confirm(self):
        observer=CombatObserver()
        self.assertFalse(observer.observe(frame(1,1000000),pixels())['temporalCandidateConfirmed'])
        self.assertFalse(observer.observe(frame(2,1000000),pixels())['temporalCandidateConfirmed'])
        self.assertFalse(observer.observe(frame(3,1625000),pixels())['temporalCandidateConfirmed'])
        self.assertTrue(observer.observe(frame(4,1937500),pixels())['temporalCandidateConfirmed'])

    def test_epoch_changes_ambiguity_and_old_sources_reset_confirmation(self):
        for current,image in ((frame(2,2000000,'other'),pixels()),(frame(2,4000000),pixels()),
                              (frame(2,2000000),pixels(((80,70,12,2),(110,95,12,2))))):
            observer=CombatObserver()
            observer.observe(frame(1,1000000),pixels())
            self.assertFalse(observer.observe(current,image)['temporalCandidateConfirmed'])

    def test_red_or_unknown_player_health_is_explicitly_unconfirmed(self):
        image=np.frombuffer(pixels(health=False),dtype=np.uint8).copy().reshape(192,192,3)
        image[180:182,80:110]=[255,90,90]
        observer=CombatObserver()
        observer.observe(frame(1,1000000),image.tobytes())
        result=observer.observe(frame(2,2000000),image.tobytes())
        self.assertEqual(result['playerHealthColor'],'red-visible')
        self.assertFalse(result['temporalCandidateConfirmed'])


if __name__=='__main__':unittest.main()
