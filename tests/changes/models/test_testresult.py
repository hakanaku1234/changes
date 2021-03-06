from base64 import b64encode

import mock

from changes.constants import Result
from changes.lib.artifact_store_mock import ArtifactStoreMock
from changes.models.failurereason import FailureReason
from changes.models.itemstat import ItemStat
from changes.models.testresult import TestResult, TestResultManager, logger
from changes.testutils.cases import TestCase


def _stat(jobstep, name):
    id = jobstep.id
    return ItemStat.query.filter_by(name=name, item_id=id)[0].value


class TestResultManagerTestCase(TestCase):
    @mock.patch('changes.models.testresult.ArtifactStoreClient', ArtifactStoreMock)
    @mock.patch('changes.storage.artifactstore.ArtifactStoreClient', ArtifactStoreMock)
    def test_simple(self):
        from changes.models.test import TestCase

        project = self.create_project()
        build = self.create_build(project)
        job = self.create_job(build)
        jobphase = self.create_jobphase(job)
        jobstep = self.create_jobstep(jobphase)
        artifact = self.create_artifact(jobstep, 'junit.xml')

        results = [
            TestResult(
                step=jobstep,
                name='test_bar',
                package='tests.changes.handlers.test_xunit',
                result=Result.failed,
                message='collection failed',
                duration=156,
                artifacts=[{
                    'name': 'artifact_name',
                    'type': 'text',
                    'base64': b64encode('sample content')}]),
            TestResult(
                step=jobstep,
                name='test_foo',
                package='tests.changes.handlers.test_coverage',
                result=Result.passed,
                message='foobar passed',
                duration=12,
                reruns=1,
            ),
        ]
        manager = TestResultManager(jobstep, artifact)
        manager.save(results)

        testcase_list = sorted(TestCase.query.all(), key=lambda x: x.name)

        assert len(testcase_list) == 2

        for test in testcase_list:
            assert test.job_id == job.id
            assert test.step_id == jobstep.id
            assert test.project_id == project.id

        assert testcase_list[0].name == 'tests.changes.handlers.test_coverage.test_foo'
        assert testcase_list[0].result == Result.passed
        assert testcase_list[0].message == 'foobar passed'
        assert testcase_list[0].duration == 12
        assert testcase_list[0].reruns == 1

        assert testcase_list[1].name == 'tests.changes.handlers.test_xunit.test_bar'
        assert testcase_list[1].result == Result.failed
        assert testcase_list[1].message == 'collection failed'
        assert testcase_list[1].duration == 156
        assert testcase_list[1].reruns is 0

        testartifacts = testcase_list[1].artifacts
        assert len(testartifacts) == 1
        assert testartifacts[0].file.get_file().read() == 'sample content'

        assert _stat(jobstep, 'test_count') == 2
        assert _stat(jobstep, 'test_failures') == 1
        assert _stat(jobstep, 'test_duration') == 168
        assert _stat(jobstep, 'test_rerun_count') == 1

        failures = FailureReason.query.filter_by(step_id=jobstep.id).all()
        assert failures == []

    @mock.patch('changes.models.testresult.ArtifactStoreClient', ArtifactStoreMock)
    @mock.patch('changes.storage.artifactstore.ArtifactStoreClient', ArtifactStoreMock)
    def test_bad_duration(self):
        from changes.models.test import TestCase

        project = self.create_project()
        build = self.create_build(project)
        job = self.create_job(build)
        jobphase = self.create_jobphase(job)
        jobstep = self.create_jobstep(jobphase)
        artifact = self.create_artifact(jobstep, 'junit.xml')

        results = [
            TestResult(
                step=jobstep,
                name='test_bar',
                package='tests.changes.handlers.test_xunit',
                result=Result.failed,
                message='collection failed',
                duration=2147483647 * 2,
                artifacts=[{
                    'name': 'artifact_name',
                    'type': 'text',
                    'base64': b64encode('sample content')}]),
        ]
        manager = TestResultManager(jobstep, artifact)

        with mock.patch.object(logger, 'warning') as warn:
            manager.save(results)
            assert warn.called

        testcase_list = TestCase.query.all()

        assert len(testcase_list) == 1

        for test in testcase_list:
            assert test.job_id == job.id
            assert test.step_id == jobstep.id
            assert test.project_id == project.id

        assert testcase_list[0].name == 'tests.changes.handlers.test_xunit.test_bar'
        assert testcase_list[0].result == Result.failed
        assert testcase_list[0].message == 'collection failed'
        assert testcase_list[0].duration == 0

    @mock.patch('changes.models.testresult.ArtifactStoreClient', ArtifactStoreMock)
    @mock.patch('changes.storage.artifactstore.ArtifactStoreClient', ArtifactStoreMock)
    def test_duplicate_tests_in_same_result_list(self):
        from changes.models.test import TestCase

        project = self.create_project()
        build = self.create_build(project)
        job = self.create_job(build)
        jobphase = self.create_jobphase(job)
        jobstep = self.create_jobstep(jobphase, label='STEP1')
        artifact = self.create_artifact(jobstep, 'junit.xml')

        results = [
            TestResult(
                step=jobstep,
                name='test_foo',
                package='project.tests',
                result=Result.passed,
                duration=12,
                reruns=0,
                artifacts=[{
                    'name': 'artifact_name',
                    'type': 'text',
                    'base64': b64encode('first artifact')}],
                message_offsets=[('system-out', 123, 10)],
            ),
            TestResult(
                step=jobstep,
                name='test_bar',
                package='project.tests',
                result=Result.passed,
                duration=13,
                reruns=0,
            ),
            TestResult(
                step=jobstep,
                name='test_foo',
                package='project.tests',
                result=Result.passed,
                duration=11,
                reruns=0,
                artifacts=[{
                    'name': 'artifact_name',
                    'type': 'text',
                    'base64': b64encode('second artifact')}],
                message_offsets=[('system-err', 555, 25)],
            ),
        ]
        manager = TestResultManager(jobstep, artifact)
        manager.save(results)

        testcase_list = sorted(TestCase.query.all(), key=lambda x: x.name)

        assert len(testcase_list) == 2

        for test in testcase_list:
            assert test.job_id == job.id
            assert test.step_id == jobstep.id
            assert test.project_id == project.id

        assert testcase_list[0].name == 'project.tests.test_bar'
        assert testcase_list[0].result == Result.passed
        assert testcase_list[0].message is None
        assert testcase_list[0].duration == 13
        assert testcase_list[0].reruns == 0
        assert len(testcase_list[0].artifacts) == 0
        assert len(testcase_list[0].messages) == 0

        assert testcase_list[1].name == 'project.tests.test_foo'
        assert testcase_list[1].result == Result.failed
        assert testcase_list[1].message.startswith('Error: Duplicate Test')
        assert testcase_list[1].message.endswith('\nSTEP1\n')
        assert testcase_list[1].duration == 12
        assert testcase_list[1].reruns == 0

        testartifacts = testcase_list[1].artifacts
        assert len(testartifacts) == 2
        a1 = testartifacts[0].file.get_file().read()
        a2 = testartifacts[1].file.get_file().read()
        assert {a1, a2} == {'first artifact', 'second artifact'}

        testmessages = testcase_list[1].messages
        assert len(testmessages) == 2
        assert testmessages[0].artifact == artifact
        assert testmessages[0].label == 'system-out'
        assert testmessages[0].start_offset == 123
        assert testmessages[0].length == 10
        assert testmessages[1].artifact == artifact
        assert testmessages[1].label == 'system-err'
        assert testmessages[1].start_offset == 555
        assert testmessages[1].length == 25

        assert _stat(jobstep, 'test_count') == 2
        assert _stat(jobstep, 'test_failures') == 1
        assert _stat(jobstep, 'test_duration') == 25
        assert _stat(jobstep, 'test_rerun_count') == 0

        failures = FailureReason.query.filter_by(step_id=jobstep.id).all()
        assert len(failures) == 1
        assert failures[0].reason == 'duplicate_test_name'

    @mock.patch('changes.models.testresult.ArtifactStoreClient', ArtifactStoreMock)
    @mock.patch('changes.storage.artifactstore.ArtifactStoreClient', ArtifactStoreMock)
    def test_duplicate_tests_in_different_result_lists(self):
        from changes.models.test import TestCase

        project = self.create_project()
        build = self.create_build(project)
        job = self.create_job(build)
        jobphase = self.create_jobphase(job)
        jobstep = self.create_jobstep(jobphase, label='STEP1')
        artifact = self.create_artifact(jobstep, 'junit.xml')

        results = [
            TestResult(
                step=jobstep,
                name='test_foo',
                package='project.tests',
                result=Result.passed,
                duration=12,
                reruns=0,
                artifacts=[{
                    'name': 'one_artifact',
                    'type': 'text',
                    'base64': b64encode('first artifact')}]
            ),
            TestResult(
                step=jobstep,
                name='test_bar',
                package='project.tests',
                result=Result.passed,
                duration=13,
                reruns=0,
            ),
        ]
        manager = TestResultManager(jobstep, artifact)
        manager.save(results)

        testcase_list = sorted(TestCase.query.all(), key=lambda x: x.name)

        assert len(testcase_list) == 2

        for test in testcase_list:
            assert test.job_id == job.id
            assert test.step_id == jobstep.id
            assert test.project_id == project.id

        assert testcase_list[0].name == 'project.tests.test_bar'
        assert testcase_list[0].result == Result.passed
        assert testcase_list[0].message is None
        assert testcase_list[0].duration == 13
        assert testcase_list[0].reruns == 0
        assert len(testcase_list[0].artifacts) == 0

        assert testcase_list[1].name == 'project.tests.test_foo'
        assert testcase_list[1].result == Result.passed
        assert testcase_list[1].message is None
        assert testcase_list[1].duration == 12
        assert testcase_list[1].reruns == 0

        testartifacts = testcase_list[1].artifacts
        assert len(testartifacts) == 1
        a1 = testartifacts[0].file.get_file().read()
        assert a1 == 'first artifact'

        assert _stat(jobstep, 'test_count') == 2
        assert _stat(jobstep, 'test_failures') == 0
        assert _stat(jobstep, 'test_duration') == 25
        assert _stat(jobstep, 'test_rerun_count') == 0

        jobstep2 = self.create_jobstep(jobphase, label='STEP2')
        artifact2 = self.create_artifact(jobstep2, 'junit.xml')

        results = [
            TestResult(
                step=jobstep2,
                name='test_foo',
                package='project.tests',
                result=Result.passed,
                duration=11,
                reruns=0,
                artifacts=[{
                    'name': 'another_artifact',
                    'type': 'text',
                    'base64': b64encode('second artifact')}]
            ),
            TestResult(
                step=jobstep2,
                name='test_baz',
                package='project.tests',
                result=Result.passed,
                duration=18,
                reruns=2,
            ),
        ]
        manager = TestResultManager(jobstep2, artifact2)
        manager.save(results)

        testcase_list = sorted(TestCase.query.all(), key=lambda x: x.name)

        assert len(testcase_list) == 3

        for test in testcase_list:
            assert test.job_id == job.id
            assert test.project_id == project.id

        assert testcase_list[0].step_id == jobstep.id
        assert testcase_list[0].name == 'project.tests.test_bar'
        assert testcase_list[0].result == Result.passed
        assert testcase_list[0].message is None
        assert testcase_list[0].duration == 13
        assert testcase_list[0].reruns == 0

        assert testcase_list[1].step_id == jobstep2.id
        assert testcase_list[1].name == 'project.tests.test_baz'
        assert testcase_list[1].result == Result.passed
        assert testcase_list[1].message is None
        assert testcase_list[1].duration == 18
        assert testcase_list[1].reruns == 2

        assert testcase_list[2].step_id == jobstep.id
        assert testcase_list[2].name == 'project.tests.test_foo'
        assert testcase_list[2].result == Result.failed
        assert testcase_list[2].message.startswith('Error: Duplicate Test')
        assert testcase_list[2].message.endswith('\nSTEP1\nSTEP2\n')
        assert testcase_list[2].duration == 12
        assert testcase_list[2].reruns == 0

        testartifacts = testcase_list[2].artifacts
        assert len(testartifacts) == 2
        a1 = testartifacts[0].file.get_file().read()
        a2 = testartifacts[1].file.get_file().read()
        assert {a1, a2} == {'first artifact', 'second artifact'}

        # Stats for original step are unharmed:

        assert _stat(jobstep, 'test_count') == 2
        assert _stat(jobstep, 'test_failures') == 1
        assert _stat(jobstep, 'test_duration') == 25
        assert _stat(jobstep, 'test_rerun_count') == 0

        # Stats for new step:

        assert _stat(jobstep2, 'test_count') == 1
        assert _stat(jobstep2, 'test_failures') == 0
        assert _stat(jobstep2, 'test_duration') == 18
        assert _stat(jobstep2, 'test_rerun_count') == 1

        failures = FailureReason.query.filter_by(step_id=jobstep.id).all()
        assert len(failures) == 0

        failures = FailureReason.query.filter_by(step_id=jobstep2.id).all()
        assert len(failures) == 1
        assert failures[0].reason == 'duplicate_test_name'
