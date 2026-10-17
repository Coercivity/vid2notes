using MassTransit;
using Vid2Notes.Api.Contracts;
using Vid2Notes.Api.Data;

namespace Vid2Notes.Api.Consumers;

public class AnalysisCompletedConsumer(AppDbContext db, ILogger<AnalysisCompletedConsumer> logger)
    : IConsumer<AnalysisCompleted>
{
    public async Task Consume(ConsumeContext<AnalysisCompleted> context)
    {
        var message = context.Message;
        var job = await db.Jobs.FindAsync([message.JobId], context.CancellationToken);
        if (job is null || job.Status != JobStatus.Analyzing)
            return;

        job.Title = message.Title;
        job.DurationSeconds = message.DurationSeconds;
        job.Width = message.Width;
        job.Height = message.Height;
        job.VideoKey = message.VideoKey;
        job.PreviewKeys = [.. message.PreviewKeys];
        job.SuggestedCrop = CropRegion.From(message.SuggestedCrop);
        job.SuggestedLayout = LayoutNames.Parse(message.SuggestedLayout);
        job.SetStatus(JobStatus.AwaitingCrop, progress: 100);
        await db.SaveChangesAsync(context.CancellationToken);
        logger.LogInformation("Job {JobId} analyzed, awaiting crop", job.Id);
    }
}
