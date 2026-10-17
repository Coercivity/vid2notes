using System.Text.Json;
using System.Text.Json.Serialization;
using MassTransit;
using Microsoft.EntityFrameworkCore;
using Vid2Notes.Api.Consumers;
using Vid2Notes.Api.Contracts;
using Vid2Notes.Api.Data;
using Vid2Notes.Api.Storage;

namespace Vid2Notes.Api.Extensions;

public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddPersistence(this IServiceCollection services, IConfiguration configuration)
    {
        services.AddDbContext<AppDbContext>(options =>
            options.UseNpgsql(configuration.GetConnectionString("Postgres")));
        return services;
    }

    public static IServiceCollection AddObjectStorage(this IServiceCollection services, IConfiguration configuration)
    {
        services.Configure<StorageOptions>(configuration.GetSection(StorageOptions.SectionName));
        services.AddSingleton<ObjectStorage>();
        return services;
    }

    public static IServiceCollection AddApi(this IServiceCollection services)
    {
        services.ConfigureHttpJsonOptions(options =>
            options.SerializerOptions.Converters.Add(new JsonStringEnumConverter(JsonNamingPolicy.CamelCase)));
        services.AddEndpointsApiExplorer();
        services.AddSwaggerGen();
        return services;
    }

    public static IServiceCollection AddMessaging(this IServiceCollection services, IConfiguration configuration)
    {
        var rabbit = configuration.GetSection("RabbitMq");

        services.AddMassTransit(x =>
        {
            x.AddEntityFrameworkOutbox<AppDbContext>(outbox =>
            {
                outbox.UsePostgres();
                outbox.UseBusOutbox();
            });

            x.AddConsumer<JobProgressConsumer>();
            x.AddConsumer<AnalysisCompletedConsumer>();
            x.AddConsumer<ExtractionCompletedConsumer>();
            x.AddConsumer<JobFailedConsumer>();

            x.UsingRabbitMq((context, cfg) =>
            {
                cfg.Host(rabbit["Host"], rabbit["VirtualHost"] ?? "/", host =>
                {
                    host.Username(rabbit["Username"] ?? "guest");
                    host.Password(rabbit["Password"] ?? "guest");
                });

                cfg.UseRawJsonSerializer(RawSerializerOptions.AnyMessageType, isDefault: true);
                cfg.UseMessageRetry(retry => retry.Intervals(500, 2000, 5000));

                cfg.AddRawEndpoint<JobProgressConsumer>(context, Queues.JobProgress);
                cfg.AddRawEndpoint<AnalysisCompletedConsumer>(context, Queues.AnalysisCompleted);
                cfg.AddRawEndpoint<ExtractionCompletedConsumer>(context, Queues.ExtractionCompleted);
                cfg.AddRawEndpoint<JobFailedConsumer>(context, Queues.JobFailed);
            });
        });

        return services;
    }

    private static void AddRawEndpoint<TConsumer>(
        this IRabbitMqBusFactoryConfigurator cfg,
        IBusRegistrationContext context,
        string queue)
        where TConsumer : class, IConsumer
    {
        cfg.ReceiveEndpoint(queue, e =>
        {
            e.ConfigureConsumeTopology = false;
            e.ConfigureConsumer<TConsumer>(context);
        });
    }
}
