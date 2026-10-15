package com.pokecollector.app.ui.scan

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.pokecollector.app.data.CardRepository
import com.pokecollector.app.data.Pricing
import com.pokecollector.app.data.api.ApiCard
import com.pokecollector.app.scan.CardTextAnalyzer
import com.pokecollector.app.scan.ScanClues
import com.pokecollector.app.ui.CardRow
import com.pokecollector.app.ui.repoViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import java.util.concurrent.Executors

sealed interface ScanState {
    data class Looking(val hint: String) : ScanState
    data class Searching(val clues: ScanClues) : ScanState
    data class Found(val clues: ScanClues, val cards: List<ApiCard>, val added: String? = null) : ScanState
    data class Failed(val message: String) : ScanState
}

class ScanViewModel(private val repo: CardRepository) : ViewModel() {
    val state = MutableStateFlow<ScanState>(ScanState.Looking(IDLE_HINT))
    private var lastKey: String? = null
    private var streak = 0

    val isLooking get() = state.value is ScanState.Looking

    /** Called for every analysed frame. Looks a card up once the same reading is seen a few times. */
    fun onClues(clues: ScanClues) {
        if (!isLooking) return
        if (clues.isEmpty) {
            streak = 0
            state.value = ScanState.Looking(IDLE_HINT)
            return
        }
        // Key on the number when we have one: names flicker more between frames than numbers do.
        val key = clues.number?.let { "$it/${clues.setTotal}" } ?: clues.key
        streak = if (key == lastKey) streak + 1 else 1
        lastKey = key
        val needed = if (clues.number != null) 2 else 4
        state.value = ScanState.Looking("Reading… " + describe(clues))
        if (streak >= needed) lookup(clues)
    }

    private fun lookup(clues: ScanClues) {
        state.value = ScanState.Searching(clues)
        viewModelScope.launch {
            state.value = runCatching { repo.identify(clues) }.fold(
                { ScanState.Found(clues, it.take(10)) },
                { ScanState.Failed("Couldn't reach the card database. Check your connection.") },
            )
        }
    }

    fun quickAdd(card: ApiCard) {
        val found = state.value as? ScanState.Found ?: return
        viewModelScope.launch {
            val variant = Pricing.defaultVariant(card)
            repo.add(card, variant)
            state.value = found.copy(added = "Added ${card.name} (${Pricing.label(variant)})")
        }
    }

    fun rescan() {
        streak = 0
        lastKey = null
        state.value = ScanState.Looking(IDLE_HINT)
    }

    companion object {
        const val IDLE_HINT = "Fill the frame with one card, flat and well lit"
        fun describe(c: ScanClues) = listOfNotNull(
            c.names.firstOrNull(),
            c.number?.let { n -> c.setTotal?.let { "$n/$it" } ?: n },
            c.hp?.let { "HP $it" },
        ).joinToString(" · ")
    }
}

@Composable
fun ScanScreen(onOpenCard: (String) -> Unit, onManualSearch: () -> Unit) {
    val context = LocalContext.current
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }
    LaunchedEffect(Unit) { if (!granted) launcher.launch(Manifest.permission.CAMERA) }

    if (!granted) {
        Column(
            Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Camera access is needed to scan cards.", textAlign = TextAlign.Center)
            Button(onClick = { launcher.launch(Manifest.permission.CAMERA) }, Modifier.padding(top = 16.dp)) {
                Text("Allow camera")
            }
            TextButton(onClick = onManualSearch) { Text("Search by name instead") }
        }
        return
    }

    val vm: ScanViewModel = viewModel(factory = repoViewModelFactory(::ScanViewModel))
    val state by vm.state.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxWidth().weight(1f)) {
            CameraPreview(paused = state !is ScanState.Looking, onClues = vm::onClues)
            // Card-shaped guide (63×88 mm).
            Box(
                Modifier
                    .align(Alignment.Center)
                    .fillMaxWidth(0.72f)
                    .aspectRatio(63f / 88f)
                    .border(3.dp, Color.White.copy(alpha = 0.85f), RoundedCornerShape(12.dp))
            )
            Surface(
                Modifier.align(Alignment.BottomCenter).padding(12.dp),
                shape = RoundedCornerShape(50),
                color = Color.Black.copy(alpha = 0.6f),
                contentColor = Color.White,
            ) {
                val hint = when (val s = state) {
                    is ScanState.Looking -> s.hint
                    is ScanState.Searching -> "Looking up " + ScanViewModel.describe(s.clues)
                    is ScanState.Found -> "Scan paused"
                    is ScanState.Failed -> "Scan paused"
                }
                Text(hint, Modifier.padding(horizontal = 16.dp, vertical = 8.dp), style = MaterialTheme.typography.bodyMedium)
            }
        }
        ResultsPanel(state, vm, onOpenCard, onManualSearch)
    }
}

@Composable
private fun ResultsPanel(
    state: ScanState,
    vm: ScanViewModel,
    onOpenCard: (String) -> Unit,
    onManualSearch: () -> Unit,
) {
    Surface(tonalElevation = 3.dp) {
        Column(Modifier.fillMaxWidth().heightIn(max = 360.dp)) {
            when (state) {
                is ScanState.Looking -> Row(
                    Modifier.fillMaxWidth().padding(8.dp),
                    horizontalArrangement = Arrangement.Center,
                ) { TextButton(onClick = onManualSearch) { Text("Can't scan it? Search by name") } }

                is ScanState.Searching -> Box(Modifier.fillMaxWidth().padding(24.dp), Alignment.Center) {
                    CircularProgressIndicator()
                }

                is ScanState.Failed -> Column(Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(state.message)
                    Button(onClick = vm::rescan, Modifier.padding(top = 8.dp)) { Text("Try again") }
                }

                is ScanState.Found -> {
                    Row(
                        Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            state.added ?: if (state.cards.isEmpty()) "No match found" else "Is it one of these?",
                            style = MaterialTheme.typography.titleSmall,
                            modifier = Modifier.weight(1f),
                        )
                        OutlinedButton(onClick = vm::rescan) { Text("Scan next") }
                    }
                    if (state.cards.isEmpty()) {
                        TextButton(onClick = onManualSearch, Modifier.padding(horizontal = 8.dp)) { Text("Search by name instead") }
                    }
                    LazyColumn {
                        items(state.cards, key = { it.id }) { card ->
                            CardRow(card, onClick = { onOpenCard(card.id) }) {
                                FilledTonalButton(onClick = { vm.quickAdd(card) }, Modifier.padding(top = 4.dp)) {
                                    Text("Add")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CameraPreview(paused: Boolean, onClues: (ScanClues) -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val analyzer = remember { CardTextAnalyzer { clues -> onClues(clues) } }
    analyzer.paused = paused
    val previewView = remember { PreviewView(context).apply { scaleType = PreviewView.ScaleType.FILL_CENTER } }

    DisposableEffect(lifecycleOwner) {
        val executor = Executors.newSingleThreadExecutor()
        val providerFuture = ProcessCameraProvider.getInstance(context)
        var provider: ProcessCameraProvider? = null
        providerFuture.addListener({
            provider = providerFuture.get().also { p ->
                val preview = Preview.Builder().build().also { it.surfaceProvider = previewView.surfaceProvider }
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                    .also { it.setAnalyzer(executor, analyzer) }
                p.unbindAll()
                p.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
            }
        }, ContextCompat.getMainExecutor(context))
        onDispose {
            provider?.unbindAll()
            executor.shutdown()
            analyzer.close()
        }
    }
    AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize().background(Color.Black))
}
