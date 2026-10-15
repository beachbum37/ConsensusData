package com.pokecollector.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.CollectionsBookmark
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.pokecollector.app.ui.collection.CollectionScreen
import com.pokecollector.app.ui.detail.CardDetailScreen
import com.pokecollector.app.ui.scan.ScanScreen
import com.pokecollector.app.ui.search.SearchScreen
import com.pokecollector.app.ui.theme.PokeCollectorTheme

private enum class Tab(val route: String, val label: String, val icon: ImageVector) {
    Collection("collection", "Collection", Icons.Default.CollectionsBookmark),
    Scan("scan", "Scan", Icons.Default.CameraAlt),
    Search("search", "Search", Icons.Default.Search),
}

class MainActivity : ComponentActivity() {
    @OptIn(ExperimentalMaterial3Api::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PokeCollectorTheme {
                val nav = rememberNavController()
                val entry by nav.currentBackStackEntryAsState()
                val route = entry?.destination?.route
                val tab = Tab.entries.firstOrNull { it.route == route }
                val openCard: (String) -> Unit = { nav.navigate("card/$it") }
                fun goTo(t: Tab) = nav.navigate(t.route) {
                    popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                    launchSingleTop = true
                    restoreState = true
                }

                Scaffold(
                    topBar = {
                        TopAppBar(
                            title = { Text(tab?.label ?: "Card") },
                            navigationIcon = {
                                if (tab == null) IconButton(onClick = { nav.popBackStack() }) {
                                    Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                                }
                            },
                        )
                    },
                    bottomBar = {
                        NavigationBar {
                            Tab.entries.forEach { t ->
                                NavigationBarItem(
                                    selected = t == tab,
                                    onClick = { goTo(t) },
                                    icon = { Icon(t.icon, null) },
                                    label = { Text(t.label) },
                                )
                            }
                        }
                    },
                ) { padding ->
                    NavHost(nav, startDestination = Tab.Collection.route, modifier = Modifier.padding(padding)) {
                        composable(Tab.Collection.route) { CollectionScreen(openCard) }
                        composable(Tab.Scan.route) { ScanScreen(openCard, onManualSearch = { goTo(Tab.Search) }) }
                        composable(Tab.Search.route) { SearchScreen(openCard) }
                        composable("card/{id}") { CardDetailScreen(it.arguments?.getString("id").orEmpty()) }
                    }
                }
            }
        }
    }
}
