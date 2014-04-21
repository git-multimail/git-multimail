package com.palantir.stash.multimail;

import java.util.List;

import org.junit.Before;
import org.junit.Ignore;
import org.junit.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

import com.atlassian.stash.hook.repository.RepositoryHookContext;
import com.atlassian.stash.repository.RefChange;
import com.atlassian.stash.server.ApplicationPropertiesService;
import com.atlassian.stash.user.StashAuthenticationContext;
import com.google.common.collect.ImmutableList;
import com.palantir.stash.multimail.admin.SettingsManager;
import com.palantir.stash.multimail.logger.PluginLoggerFactory;

public class StashGitMultimailTest {

    private StashGitMultimail sgm;
    private PluginLoggerFactory loggerFactory;

    @Mock
    private ApplicationPropertiesService appService;
    @Mock
    private StashAuthenticationContext authContext;
    @Mock
    private SettingsManager settingsManager;

    @Mock
    private RepositoryHookContext rhc;
    @Mock
    private RefChange refChangeA;
    @Mock
    private RefChange refChangeB;

    @Before
    public void setUp() {
        MockitoAnnotations.initMocks(this);

        loggerFactory = new PluginLoggerFactory();
        sgm = new StashGitMultimail(appService, authContext, settingsManager, loggerFactory);
    }

    @Test
    @Ignore
    public void testSomething() {

        List<RefChange> changes = ImmutableList.of(refChangeA, refChangeB);
        sgm.postReceive(rhc, changes);

        // TODO: pass in a mock executor pool, ensure that an executor is requested and the proper call made on it
    }
}
