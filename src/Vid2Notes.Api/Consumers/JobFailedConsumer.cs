using MassTransit;
using Vid2Notes.Api.Contracts;
using Vid2Notes.Api.Data;

namespace Vid2Notes.Api.Consumers;

public class JobFailedConsumer(AppDbContext db, ILogger<JobFailedConsumer> logger) : IConsumer<JobFailed>
{
    public async Task Consume(ConsumeContext<JobFailed> context)
    {
        var message = context.Message;
        var job = await db.Jobs.FindAsync([message.JobId], context.CancellationToken);
        if (job is null || job.Status is not (JobStatus.Analyzing or JobStatus.Extracting))
            return;

        job.Error = message.Reason;
        job.SetStatus(JobStatus.Failed, message.Stage);
        await db.SaveChangesAsync(context.CancellationToken);
        logger.LogWarning("Job {JobId} failed at {Stage}: {Reason}", job.Id, message.Stage, message.Reason);
    }
}
