using MassTransit;
using Vid2Notes.Api.Contracts;
using Vid2Notes.Api.Data;

namespace Vid2Notes.Api.Consumers;

public class ExtractionCompletedConsumer(AppDbContext db, ILogger<ExtractionCompletedConsumer> logger)
    : IConsumer<ExtractionCompleted>
{
    public async Task Consume(ConsumeContext<ExtractionCompleted> context)
    {
        var message = context.Message;
        var job = await db.Jobs.FindAsync([message.JobId], context.CancellationToken);
        if (job is null || job.Status != JobStatus.Extracting)
            return;

        job.PdfKey = message.PdfKey;
        job.PageCount = message.PageCount;
        job.MidiKey = message.MidiKey;
        job.NoteCount = message.NoteCount;
        job.MusicXmlKey = message.MusicXmlKey;
        job.Tempo = message.Tempo;
        job.TimeSignature = message.TimeSignature;
        job.KeyName = message.KeyName;
        job.Error = null;
        job.SetStatus(JobStatus.Completed, progress: 100);
        await db.SaveChangesAsync(context.CancellationToken);
        logger.LogInformation(
            "Job {JobId} completed: {Pages} pages, {Notes} notes",
            job.Id,
            message.PageCount,
            message.NoteCount);
    }
}
