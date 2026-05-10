import PageStub from '@/components/PageStub';

export default function LifecycleManager() {
  return (
    <PageStub
      title="Lifecycle Manager"
      batch={6}
      summary="6-state kanban (active / high_value / decay / inactive / proposed / retired); weighted multi-signal scoring."
    />
  );
}
