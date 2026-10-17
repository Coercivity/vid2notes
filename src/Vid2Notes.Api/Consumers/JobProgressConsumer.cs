using MassTransit;
using Vid2Notes.Api.Contracts;
using Vid2Notes.Api.Data;

namespace Vid2Notes.Api.Consumers;

public class JobProgressConsumer(AppDbContext db) : IConsumer<JobProgress>
{
    public async Task Consume(ConsumeContext<JobProgress> context)
    {
        var message = context.Message;
        var job = await db.Jobs.FindAsync([message.JobId], context.CancellationToken);
        if (job is null || job.Status is not (JobStatus.Analyzing or JobStatus.Extracting))
            return;

        job.SetStatus(job.Status, message.Stage, Math.Clamp(message.Percent, 0, 100));
        await db.SaveChangesAsync(context.CancellationToken);
    }
}
