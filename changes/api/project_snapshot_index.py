from __future__ import absolute_import

from flask.ext.restful.reqparse import RequestParser
from sqlalchemy.orm import joinedload

from changes.api.base import APIView
from changes.api.build_index import identify_revision, MissingRevision
from changes.config import db
from changes.constants import Cause, Status
from changes.db.utils import get_or_create
from changes.jobs.create_job import create_job
from changes.jobs.sync_build import sync_build
from changes.models import (
    Build, Job, JobPlan, Project, Snapshot, SnapshotImage, SnapshotStatus,
    Source
)


class ProjectSnapshotIndexAPIView(APIView):
    post_parser = RequestParser()
    post_parser.add_argument('sha', type=str, required=True)

    def get(self, project_id):
        project = Project.get(project_id)
        if not project:
            return '', 404

        queryset = Snapshot.query.options(
            joinedload('source').joinedload('revision'),
        ).filter(
            Snapshot.project_id == project.id,
        ).order_by(
            Snapshot.date_created.desc(),
        )

        return self.paginate(queryset)

    def post(self, project_id):
        """Initiates a new snapshot for this project."""
        project = Project.get(project_id)
        if not project:
            return '', 404

        args = self.post_parser.parse_args()

        repository = project.repository

        try:
            revision = identify_revision(repository, args.sha)
        except MissingRevision:
            # if the default fails, we absolutely can't continue and the
            # client should send a valid revision
            return '{"error": "Unable to find a matching revision."}', 400

        if revision:
            sha = revision.sha
        else:
            sha = args.sha

        plan_list = list(project.plans)
        if not plan_list:
            return '{"error": "No plans associated with project."}', 400

        source, _ = get_or_create(Source, where={
            'repository': repository,
            'revision_sha': sha,
        })

        build = Build(
            source_id=source.id,
            source=source,
            project_id=project.id,
            project=project,
            label='Create Snapshot',
            status=Status.queued,
            cause=Cause.snapshot,
            target=sha[:12],
        )
        db.session.add(build)

        # TODO(dcramer): this needs to update with the build result
        snapshot = Snapshot(
            project_id=project.id,
            source_id=source.id,
            build_id=build.id,
            status=SnapshotStatus.pending,
        )
        db.session.add(snapshot)

        jobs = []
        for plan in plan_list:
            job = Job(
                build=build,
                build_id=build.id,
                project=project,
                project_id=project.id,
                source=build.source,
                source_id=build.source_id,
                status=build.status,
                label='Create Snapshot: %s' % (plan.label,),
            )
            db.session.add(job)

            jobplan = JobPlan.build_jobplan(plan, job)
            db.session.add(jobplan)

            image = SnapshotImage(
                job=job,
                snapshot=snapshot,
                plan=plan,
            )
            db.session.add(image)

            jobs.append(job)

        db.session.commit()

        for job in jobs:
            create_job.delay(
                job_id=job.id.hex,
                task_id=job.id.hex,
                parent_task_id=job.build_id.hex,
            )

        db.session.commit()

        sync_build.delay(
            build_id=build.id.hex,
            task_id=build.id.hex,
        )

        return self.respond(snapshot)