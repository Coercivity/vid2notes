using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace Vid2Notes.Api.Data.Configurations;

public class JobConfiguration : IEntityTypeConfiguration<Job>
{
    public void Configure(EntityTypeBuilder<Job> job)
    {
        job.HasKey(j => j.Id);
        job.Property(j => j.Url).HasMaxLength(2048);
        job.Property(j => j.Status).HasConversion<string>().HasMaxLength(32);
        job.Property(j => j.SuggestedLayout).HasConversion<string>().HasMaxLength(16);
        job.Property(j => j.Layout).HasConversion<string>().HasMaxLength(16);
        job.Property(j => j.Stage).HasMaxLength(32);
        job.OwnsOne(j => j.SuggestedCrop);
        job.OwnsOne(j => j.Crop);
        job.HasIndex(j => j.CreatedAt);
    }
}
